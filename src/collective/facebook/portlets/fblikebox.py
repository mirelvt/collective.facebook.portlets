# -*- coding: utf-8 -*-
from zope.interface import implements

from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base

from zope import schema

from zope.formlib import form
from zope.schema.vocabulary import SimpleVocabulary, SimpleTerm

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile

from collective.facebook.portlets.config import PROJECTNAME

from zope.security import checkPermission

from collective.facebook.portlets import _

import logging

logger = logging.getLogger(PROJECTNAME)

color_scheme = SimpleVocabulary([SimpleTerm(value=u'light', title=_(u'Light')),
                                 SimpleTerm(value=u'dark', title=_(u'Dark'))]
                                )


class IFacebookLikeBoxPortlet(IPortletDataProvider):
    """A portlet

    It inherits from IPortletDataProvider because for this portlet, the
    data that is being rendered and the portlet assignment itself are the
    same.
    """

    header = schema.TextLine(title=_(u'Header'),
                             description=_(u"The header for the portlet. "
                                           "Leave empty for none."),
                             required=False)

    api_key = schema.TextLine(title=_(u'API key'),
                              description=_(u"The key for the app "
                                            "to be used."),
                              required=True)

    page_url = schema.TextLine(title=_(u'Facebook Page URL'),
                               description=_(u"the URL of the Facebook Page "
                                             "for this Like Box."),
                               required=False)

    width = schema.Int(title=_(u'Width'),
                       description=_(u"Width of the portlet."),
                       required=True,
                       default=300)

    height = schema.Int(title=_(u'Height'),
                        description=_(u"Height of the portlet."),
                        required=True,
                        default=300)

    color_scheme = schema.Choice(title=_(u'Color Scheme'),
                                 description=_(u"The color scheme to use"),
                                 required=True,
                                 vocabulary=color_scheme)

    border_color = schema.TextLine(title=_(u'Border color'),
                                   description=_(u"The border color "
                                                 "to use (hex)."),
                                   required=False)

    show_faces = schema.Bool(title=_(u'Show Faces'),
                             description=_(u"Specifies whether or not "
                                           "to display profile photos "
                                           "in the plugin."),
                             required=False,
                             default=True)

    show_stream = schema.Bool(title=_(u'Show Stream'),
                              description=_(u"Specifies whether to "
                                            "display a stream of the latest "
                                            "posts from the Page's wall."),
                              required=False,
                              default=True)

    show_header = schema.Bool(title=_(u'Show Facebook header'),
                              description=_(u"Specifies whether to "
                                            "display the Facebook header "
                                            "at the top of the plugin."),
                              required=False,
                              default=True)

    force_wall = schema.Bool(title=_(u'Force Wall'),
                             description=_(u"For Places, specifies whether "
                                           "the stream contains posts from "
                                           "the Place's wall or just checkins "
                                           "from friends."),
                             required=False,
                             default=False)


class Assignment(base.Assignment):
    """Portlet assignment.

    This is what is actually managed through the portlets UI and associated
    with columns.
    """

    implements(IFacebookLikeBoxPortlet)

    header = u""
    api_key = u""
    page_url = u""
    width = 300
    height = 300
    color_scheme = u"light"
    target = u"_blank"
    border_color = u""
    show_faces = True
    show_stream = True
    show_header = True
    force_wall = False

    def __init__(self,
                 api_key,
                 page_url,
                 header=u"",
                 width=300,
                 height=300,
                 color_scheme=u"light",
                 target=u"_blank",
                 border_color=u"",
                 show_faces=True,
                 show_stream=True,
                 show_header=True,
                 force_wall=False):

        self.header = header
        self.api_key = api_key
        self.page_url = page_url
        self.width = width
        self.height = height
        self.color_scheme = color_scheme
        self.target = target
        self.border_color = border_color
        self.show_faces = show_faces
        self.show_stream = show_stream
        self.show_header = show_header
        self.force_wall = force_wall

    @property
    def title(self):
        """This property is used to give the title of the portlet in the
        "manage portlets" screen.
        """
        return _(u"Facebook Like Box")


class Renderer(base.Renderer):
    """Portlet renderer.

    This is registered in configure.zcml. The referenced page template is
    rendered, and the implicit variable 'view' will refer to an instance
    of this class. Other methods can be added and referenced in the template.
    """

    render = ViewPageTemplateFile('fblikebox.pt')

    def getHeader(self):
        """
        Returns the header for the portlet
        """
        return self.data.header

    def getJsCode(self):

        js_code = """
        (function(d, s, id) {
            var js, fjs = d.getElementsByTagName(s)[0];
            if (d.getElementById(id)) return;
            js = d.createElement(s); js.id = id;
            js.src = "//connect.facebook.net/en_US/all.js#xfbml=1&appId=%s";
            fjs.parentNode.insertBefore(js, fjs);
            }(document, 'script', 'facebook-jssdk'));
            """ % self.data.api_key

        return js_code


class AddForm(base.AddForm):
    """Portlet add form.

    This is registered in configure.zcml. The form_fields variable tells
    zope.formlib which fields to display. The create() method actually
    constructs the assignment that is being added.
    """
    form_fields = form.Fields(IFacebookLikeBoxPortlet)

    def create(self, data):
        return Assignment(**data)


class EditForm(base.EditForm):
    """Portlet edit form.

    This is registered with configure.zcml. The form_fields variable tells
    zope.formlib which fields to display.
    """
    form_fields = form.Fields(IFacebookLikeBoxPortlet)
