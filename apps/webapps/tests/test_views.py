from nose.tools import eq_
from pyquery import PyQuery as pq

from amo.helpers import absolutify, page_title
import amo.tests
from amo.urlresolvers import reverse
from addons.models import Addon, AddonUser
from addons.tests.test_views import add_addon_author, test_hovercards
from browse.tests import test_listing_sort, test_default_sort
from django.utils.encoding import iri_to_uri
from sharing import SERVICES
from translations.helpers import truncate
from users.models import UserProfile
from versions.models import Version
from webapps.models import Webapp


class WebappTest(amo.tests.TestCase):

    def setUp(self):
        self.webapp = Webapp.objects.create(name='woo', app_slug='yeah',
                                            status=amo.STATUS_PUBLIC)
        self.webapp._current_version = (Version.objects
                                        .create(addon=self.webapp))
        self.webapp.save()

        self.url = self.webapp.get_url_path()


class TestLayout(WebappTest):

    def test_header(self):
        response = self.client.get(self.url)
        doc = pq(response.content)
        eq_(doc('h1.site-title').text(), 'Apps')
        eq_(doc('#site-nav.app-nav').length, 1)
        eq_(doc('#search-q').attr('placeholder'), 'search for apps')
        eq_(doc('#id_cat').attr('value'), 'apps')

    def test_footer(self):
        response = self.client.get(self.url)
        eq_(pq(response.content)('#social-footer').length, 0)


class TestListing(WebappTest):

    def setUp(self):
        self.url = reverse('apps.list')

    def test_default_sort(self):
        test_default_sort(self, 'downloads', 'weekly_downloads')

    def test_rating_sort(self):
        test_listing_sort(self, 'rating', 'bayesian_rating')

    def test_newest_sort(self):
        test_listing_sort(self, 'created', 'created')

    def test_name_sort(self):
        test_listing_sort(self, 'name', 'name', reverse=False,
                          sel_class='extra-opt')

    def test_featured_sort(self):
        test_listing_sort(self, 'featured', sel_class='extra-opt')

    def test_updated_sort(self):
        test_listing_sort(self, 'updated', 'last_updated',
                          sel_class='extra-opt')

    def test_upandcoming_sort(self):
        test_listing_sort(self, 'hotness', 'hotness', sel_class='extra-opt')


class TestDetail(WebappTest):
    fixtures = ['base/apps', 'base/addon_3615', 'base/addon_592', 'base/users']

    def get_more_pq(self):
        more_url = self.webapp.get_url_path(more=True)
        return pq(self.client.get_ajax(more_url).content.decode('utf-8'))

    def test_title(self):
        response = self.client.get(self.url)
        eq_(pq(response.content)('title').text(), 'woo :: Apps Marketplace')

    def test_more_url(self):
        response = self.client.get(self.url)
        eq_(pq(response.content)('#more-webpage').attr('data-more-url'),
            self.webapp.get_url_path(more=True))

    def test_headings(self):
        response = self.client.get(self.url)
        doc = pq(response.content)
        eq_(doc('#addon h1').text(), 'woo')
        eq_(doc('h2:first').text(), 'About this App')

    def test_reviews(self):
        eq_(self.get_more_pq()('#reviews h3').remove('a').text(),
            'This app has not yet been reviewed.')

    def test_other_apps(self):
        """Ensure listed apps by the same author show up."""
        # Create a new webapp.
        Addon.objects.get(id=592).update(type=amo.ADDON_WEBAPP)
        other = Webapp.objects.get(id=592)
        eq_(list(Webapp.objects.listed().exclude(id=self.webapp.id)), [other])

        author = add_addon_author(other, self.webapp)
        doc = self.get_more_pq()('#author-addons')
        eq_(doc.length, 1)

        by = doc.find('h2 a')
        eq_(by.attr('href'), author.get_url_path())
        eq_(by.text(), author.name)

        test_hovercards(self, doc, [other], src='dp-dl-othersby')

    def test_other_apps_no_addons(self):
        """An add-on by the same author should not show up."""
        other = Addon.objects.get(id=592)
        assert other.type != amo.ADDON_WEBAPP, 'Should not be an app.'

        add_addon_author(other, self.webapp)
        eq_(self.get_more_pq()('#author-addons').length, 0)

    def test_other_apps_no_unlisted(self):
        """An unlisted app by the same author should not show up."""
        Addon.objects.get(id=592).update(type=amo.ADDON_WEBAPP,
                                         disabled_by_user=True)
        other = Webapp.objects.get(id=592)

        add_addon_author(other, self.webapp)
        eq_(self.get_more_pq()('#author-addons').length, 0)

    def test_other_apps_by_others(self):
        """Apps by different/no authors should not show up."""
        author = UserProfile.objects.get(pk=999)
        AddonUser.objects.create(addon=self.webapp, user=author, listed=True)
        eq_(self.get_more_pq()('#author-addons').length, 0)

    def test_other_apps_none(self):
        eq_(self.get_more_pq()('#author-addons').length, 0)


class TestMobileDetail(amo.tests.MobileTest, WebappTest):

    def test_page(self):
        r = self.client.get(self.url)
        eq_(r.status_code, 200)
        self.assertTemplateUsed(r, 'addons/mobile/details.html')

    def test_no_release_notes(self):
        r = self.client.get(self.url)
        eq_(pq(r.content)('.versions').length, 0)


class TestSharing(WebappTest):

    def test_redirect_sharing(self):
        r = self.client.get(reverse('apps.share', args=['yeah']),
                            {'service': 'delicious'})
        d = {
            'title': page_title({'request': r}, self.webapp.name,
                                force_webapps=True),
            'description': truncate(self.webapp.summary, length=250),
            'url': absolutify(self.webapp.get_url_path()),
        }
        url = iri_to_uri(SERVICES['delicious'].url.format(**d))
        self.assertRedirects(r, url, status_code=302, target_status_code=301)
