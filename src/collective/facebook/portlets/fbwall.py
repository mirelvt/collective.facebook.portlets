# -*- coding: utf-8 -*-
from zope.interface import implements
from zope.interface import alsoProvides

from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base

from zope import schema
from zope.component import getUtility

from zope.formlib import form
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from plone.registry.interfaces import IRegistry
from zope.schema.interfaces import IContextSourceBinder
from collective.prettydate.interfaces import IPrettyDate

from collective.facebook.portlets import _
from collective.facebook.portlets.config import GRAPH_URL
from collective.facebook.portlets.config import PROJECTNAME

from zope.security import checkPermission

from plone.memoize import ram
from time import time

from DateTime import DateTime

import json
import urllib

import logging

logger = logging.getLogger(PROJECTNAME)


def FacebookAccounts(context):
    registry = getUtility(IRegistry)
    accounts = registry['collective.facebook.accounts']
    if accounts:
        keys = accounts.keys()
    else:
        keys = []

    if keys:
        for i in keys:
            vocab = SimpleVocabulary(
            [SimpleTerm(value=id, title=accounts[id]['name']) for id in keys])
    else:
        vocab = SimpleVocabulary.fromValues(keys)

    return vocab


alsoProvides(FacebookAccounts, IContextSourceBinder)


def cache_key_simple(func, var):
    #let's memoize for 20 minutes or if any value of the portlet is modified
    timeout = time() // (60 * 20)
    return (timeout,
            var.data.wall_id,
            var.data.only_self,
            var.data.max_results)


class IFacebookWallPortlet(IPortletDataProvider):
    """A portlet

    It inherits from IPortletDataProvider because for this portlet, the
    data that is being rendered and the portlet assignment itself are the
    same.
    """

    header = schema.TextLine(title=_(u'Header'),
                             description=_(u"The header for the portlet. "
                                            "Leave empty for none."),
                             required=False)

    fb_account = schema.Choice(title=_(u'Facebook account'),
                               description=_(u"Which Facebook account to "
                                              "use."),
                               required=True,
                               source=FacebookAccounts)

    wall_id = schema.TextLine(title=_(u'Wall ID'),
                              description=_(u"ID for the wall you are trying "
                                             "to fetch from. More info in: "
                                             "https://developers.facebook.com/"
                                             "docs/reference/api/"),
                              required=True)

    max_results = schema.Int(title=_(u'Maximum results'),
                             description=_(u"The maximum results number."),
                             required=True,
                             default=5)

    only_self = schema.Bool(title=_(u'Show only from owner'),
                            description=_(u"Only show posts made by the "
                                           "wall owner."),
                            required=False)

    pretty_date = schema.Bool(title=_(u'Pretty dates'),
                              description=_(u"Show dates in a pretty format "
                                             "(ie. '4 hours ago')."),
                              default=True,
                              required=False)


class Assignment(base.Assignment):
    """Portlet assignment.

    This is what is actually managed through the portlets UI and associated
    with columns.
    """

    implements(IFacebookWallPortlet)

    header = u""
    fb_account = u""
    wall_id = u""
    max_results = 20
    only_self = False
    pretty_date = True

    def __init__(self,
                 fb_account,
                 wall_id,
                 max_results,
                 header=u"",
                 only_self=False,
                 pretty_date=True):

        self.header = header
        self.fb_account = fb_account
        self.wall_id = wall_id
        self.max_results = max_results
        self.only_self = only_self
        self.pretty_date = pretty_date

    @property
    def title(self):
        """This property is used to give the title of the portlet in the
        "manage portlets" screen.
        """
        return _(u"Facebook wall Portlet")


MAX_FETCHES = 15


class Renderer(base.Renderer):
    """Portlet renderer.

    This is registered in configure.zcml. The referenced page template is
    rendered, and the implicit variable 'view' will refer to an instance
    of this class. Other methods can be added and referenced in the template.
    """

    render = ViewPageTemplateFile('fbwall.pt')

    def getHeader(self):
        """
        Returns the header for the portlet
        """
        return self.data.header

    def canEdit(self):
        return checkPermission('cmf.ModifyPortalContent', self.context)

    def isValidAccount(self):
        registry = getUtility(IRegistry)
        accounts = registry.get('collective.facebook.accounts', None)

        if self.data.fb_account not in accounts:
            logger.debug("The account '%s' is invalid." % self.data.fb_account)
            return False
        else:
            logger.debug("'%s' is a valid account." % self.data.fb_account)
            if accounts[self.data.fb_account]['expires']:
                expires = DateTime(accounts[self.data.fb_account]['expires'])
                if expires and expires < DateTime():
                    logger.debug("But it already expired...")
                    return False

        return True

    @ram.cache(cache_key_simple)
    def getSearchResults(self):
        logger.debug("Going to Facebook to fetch results.")
        registry = getUtility(IRegistry)
        accounts = registry.get('collective.facebook.accounts', None)

        result = []
        if self.data.fb_account in accounts:
            logger.debug("Using account '%s'" % self.data.fb_account)
            access_token = accounts[self.data.fb_account]['access_token']

            wall = self.data.wall_id + '/feed'
            params = access_token + '&limit=%s' % self.data.max_results
            url = GRAPH_URL % (wall, params)

            logger.debug("URL: %s" % url)
            query_result = json.load(urllib.urlopen(url))

            # I wanted to do this using fql, but i couldn't
            # Specificaly, i couldn't find a way to obtain links titles
            # I managed to get this:
            # /fql?q=SELECT+created_time,message,comments,likes,action_links,
            #               message_tags+FROM+stream+
            #        WHERE+filter_key+=+'owner'+
            #        AND+source_id+=+[uid]&access_token=
            if self.data.only_self:
                logger.debug("Only get posts from self.")
                # Let's get the ID for the wall owner
                uurl = GRAPH_URL % (self.data.wall_id, access_token)
                logger.debug("URL to get ID: %s" % uurl)
                account_data = json.load(urllib.urlopen(uurl))
                uid = None
                if 'id' in account_data.keys():
                    uid = account_data['id']

            # Now, let's iterate on each result until we have the amount
            # we wanted
            logger.debug("About to start getting results...")
            #we need to give a max number of fetches.. or we may have a big
            #and long loop
            fetch_number = 0
            while ('paging' in query_result and
                    len(result) < self.data.max_results and
                    fetch_number < MAX_FETCHES):
                try:
                    post = query_result['data'].pop(0)
                except IndexError:
                    logger.debug("%s results so far. Need to fetch "
                                 "some more..." % len(result))
                    # If we are here, it means, we need to query for the
                    # next page of results
                    fetch_number += 1
                    url = query_result['paging']['next']
                    logger.debug("Next URL: %s" % url)
                    query_result = json.load(urllib.urlopen(url))
                post['avatar'] = "http://graph.facebook.com/%s/picture" % \
                    post['from']['id']
                post['username'] = post['from']['name']
                post['user_url'] = "http://www.facebook.com/%s" % \
                    post['from']['id']
                if 'object_id' in post.keys():
                    post['post_url'] = "http://www.facebook.com/%s" % \
                        post['object_id']
                if self.data.only_self:
                    if post['from']['id'] == uid:
                        result.append(post)
                else:
                    result.append(post)
        logger.debug("Done. returning %s results" % len(result))
        return result

    def getFacebookLink(self):

        return "https://www.facebook.com/%s" % self.data.wall_id

    def getDate(self, str_date):
        if self.data.pretty_date:
            # Returns human readable date for the wall post
            date_utility = getUtility(IPrettyDate)
            date = date_utility.date(str_date)
        else:
            date = DateTime(str_date)

        return date


class AddForm(base.AddForm):
    """Portlet add form.

    This is registered in configure.zcml. The form_fields variable tells
    zope.formlib which fields to display. The create() method actually
    constructs the assignment that is being added.
    """
    form_fields = form.Fields(IFacebookWallPortlet)

    def create(self, data):
        return Assignment(**data)


class EditForm(base.EditForm):
    """Portlet edit form.

    This is registered with configure.zcml. The form_fields variable tells
    zope.formlib which fields to display.
    """
    form_fields = form.Fields(IFacebookWallPortlet)
