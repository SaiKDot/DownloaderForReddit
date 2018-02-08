"""
Downloader for Reddit takes a list of reddit users and subreddits and downloads content posted to reddit either by the
users or on the subreddits.


Copyright (C) 2017, Kyle Hickey


This file is part of the Downloader for Reddit.

Downloader for Reddit is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Downloader for Reddit is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Downloader for Reddit.  If not, see <http://www.gnu.org/licenses/>.
"""


import requests
from bs4 import BeautifulSoup
from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError, ImgurClientRateLimitError
import logging

from Core.Content import Content
import Core.Injector
from Core.Post import Post


class Extractor(object):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        """
        A class that handles extracting individual item urls from the hosting websites.  Interacts with website APIs if
        available and directly with requests if not.

        :param url: The url of the link posted to reddit
        :param user: The name of the user that posted the link to reddit
        :param post_title: The title of the post that was submitted to reddit
        :param subreddit: The subreddit the post was submitted to
        :param creation_date: The date when the post was submitted to reddit
        """
        self.logger = logging.getLogger('DownloaderForReddit.%s' % __name__)
        self.settings_manager = Core.Injector.get_settings_manager()
        self.url = url
        self.user = user
        self.post_title = post_title
        self.subreddit = subreddit
        self.creation_date = creation_date
        self.save_path = save_path
        self.content_display_only = content_display_only
        self.subreddit_save_method = subreddit_save_method
        self.name_downloads_by = name_downloads_by
        self.extracted_content = []
        self.failed_extract_messages = []
        self.failed_extracts_to_save = []

    def get_json(self, url):
        """Makes sure that a request is valid and handles without errors if the connection is not successful"""
        response = requests.get(url)
        if response.status_code == 200 and 'json' in response.headers['Content-Type']:
            return response.json()
        else:
            self.logger.error('Failed connection: Bad response', extra={'response_code': response.status_code,
                                                                        'extractor_data': self.get_log_data()})
            self.extracted_content.append("Failed to retrieve json data for link %s\nUser: %s  Subreddit: %s  Tile: %s"
                                          % (url, self.user, self.subreddit, self.post_title))

    def get_text(self, url):
        """See get_json"""
        response = requests.get(url)
        if response.status_code == 200 and 'text' in response.headers['Content-Type']:
            return response.text
        else:
            self.logger.error('Failed connection: Bad response', extra={'response_code': response.status_code,
                                                                        'extractor_data': self.get_log_data()})
            self.extracted_content.append("Failed to retrieve data for link %s\nUser: %s  Subreddit: %s  Tile: %s" %
                                          (url, self.user, self.subreddit, self.post_title))

    def make_content(self, url, file_name, count, extension, date_created):
        count = ' %s' % count if count else ''
        x = Content(url, self.user, self.post_title, self.subreddit, file_name, count, '.' + extension, self.save_path,
                    self.subreddit_save_method, date_created, self.content_display_only)
        self.extracted_content.append(x)

    def get_log_data(self):
        return {'url': self.url,
                'user': self.user,
                'subreddit': self.subreddit,
                'post_title': self.post_title,
                'creation_date': self.creation_date,
                'save_path': self.save_path,
                'content_display_only': self.content_display_only,
                'subreddit_save_method': self.subreddit_save_method,
                'name_downloads_by': self.name_downloads_by,
                'extracted_content_count': len(self.extracted_content),
                'failed_extract_message_count': len(self.failed_extract_messages),
                'failed_extracts_to_save_count': len(self.failed_extracts_to_save)}


class ImgurExtractor(Extractor):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        """
        A subclass of the Extractor class.  This class interacts exclusively with the imgur website through the imgur
        api via ImgurPython

        :param imgur_client: A tuple of the client id and client secret provided by imgur to access their api.  This
        tuple is supplied to imgurpython to establish an imgur client
        """
        super().__init__(url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                         save_path, content_display_only)
        self.imgur_client_id = self.settings_manager.imgur_client_id
        self.imgur_client_secret = self.settings_manager.imgur_client_secret
        if self.imgur_client_id is None or self.imgur_client_secret is None:
            self.logger.warning('Imgur extract failed: No imgur client setup',
                                extra={'url': self.url, 'user': self.user, 'subreddit': self.subreddit,
                                       'post_title': self.post_title, 'creation_date': self.creation_date})
            self.failed_extract_messages.append('\nFailed: No valid Imgur client is detected. In order to download '
                                                'content from imgur.com you must have a valid Imugr client. Please see'
                                                'the settings menu.\nTitle: %s,  User: %s,  Subreddit: %s,  URL: %s\n' %
                                                (self.post_title, self.user, self.subreddit, self.url))
        else:
            try:
                self.client = ImgurClient(self.imgur_client_id, self.imgur_client_secret)
            except ImgurClientError as e:
                if e.status_code == 500:
                    self.over_capacity_error()

    def extract_content(self):
        """Dictates what type of page container a link is and then dictates which extraction method should be used"""
        try:
            if 'i.imgur' in self.url:
                self.extract_direct_link()

            elif "/a/" in self.url:
                self.extract_album()
            elif '/gallery/' in self.url:
                try:
                    self.extract_album()
                except:
                    pass
            elif self.url.lower().endswith(('.jpg', 'jpeg', '.png', '.gif', '.gifv', '.mp4', '.webm')):
                self.extract_direct_mislinked()
            else:
                self.extract_single()
        except ImgurClientError as e:

            if e.status_code == 403:
                if self.client.credits['ClientRemaining'] is None:
                    self.failed_to_locate_error()
                elif self.client.credits['ClientRemaining'] <= 0:
                    self.no_credit_error()
                else:
                    self.failed_to_locate_error()
            if e.status_code == 429:
                self.rate_limit_exceeded_error()
            if e.status_code == 500:
                self.over_capacity_error()
            if e.status_code == 404:
                self.does_not_exist_error()
        except ImgurClientRateLimitError:
            self.rate_limit_exceeded_error()
        except:
            self.failed_to_locate_error()

    def rate_limit_exceeded_error(self):
        x = Post(self.url, self.user, self.post_title, self.subreddit, self.creation_date)
        self.failed_extracts_to_save.append(x)
        self.failed_extract_messages.append('\nFailed: Imgur rate limit exceeded.  This post has been saved and will '
                                            'be downloaded the next time the application is run.  Please make sure you '
                                            'have adequate user credits upon the next run.  User credits can be '
                                            'checked in the help menu\nTitle: %s,  User: %s,  Subreddit: %s' %
                                            (self.post_title, self.user, self.subreddit))
        self.logger.error('Failed extract: Rate limit exceeded', extra={'extractor_data': self.get_log_data()})

    def no_credit_error(self):
        x = Post(self.url, self.user, self.post_title, self.subreddit, self.creation_date)
        self.failed_extracts_to_save.append(x)
        self.failed_extract_messages.append('\nFailed: You do not have enough imgur credits left to extract this '
                                            'content.  This post will be saved and extraction attempted '
                                            'the next time the program is run.  Please make sure that you '
                                            'have adequate credits upon next run.\nTitle: %s,  User: %s,  '
                                            'Subreddit: %s' % (self.post_title, self.user, self.subreddit))
        self.logger.error('Failed extract: Out of credits', extra={'extractor_data': self.get_log_data()})

    def over_capacity_error(self):
        x = Post(self.url, self.user, self.post_title, self.subreddit, self.creation_date)
        self.failed_extracts_to_save.append(x)
        self.failed_extract_messages.append('\nFailed: Imgur is currently over capacity.  This post has been saved and '
                                            'extraction will be attempted the next time the program is run.\nTitle: '
                                            '%s, User: %s,  Subreddit: %s' % (self.post_title, self.user,
                                                                              self.subreddit))
        self.logger.error('Failed extract: Imgur over capacity', extra={'extractor_data': self.get_log_data()})

    def does_not_exist_error(self):
        self.failed_extract_messages.append('\nFailed: The content does not exist.  This most likely means that the '
                                            'image has been deleted on Imgur, but the post still remains on reddit\n'
                                            'Url: %s,  User: %s,  Subreddit: %s,  Title: %s' % (self.url, self.user,
                                                                                                self.subreddit,
                                                                                                self.post_title))
        self.logger.warning('Failed extract: Content no longer exists', extra={'extractor_data': self.get_log_data()})

    def failed_to_locate_error(self):
        self.failed_extract_messages.append('\nFailed to locate the content at %s\nUser: %s  Subreddit: %s  Title: %s'
                                            '\n' % (self.url, self.user, self.subreddit, self.post_title))
        self.logger.error('Failed extract: Failed to locate content', extra={'extractor_data': self.get_log_data()})

    def extract_direct_link(self):
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.gifv', '.mp4', '.webm']:
            if ext in self.url:
                index = self.url.find(ext)
                url = '%s%s' % (self.url[:index], ext)

        try:
            domain, id_with_ext = url.rsplit('/', 1)
            image_id, extension = id_with_ext.rsplit('.', 1)
            file_name = self.post_title if self.name_downloads_by == 'Post Title' else image_id
            if url.endswith('gifv') or url.endswith('gif'):
                picture = self.client.get_image(image_id)
                if picture.type == 'image/gif' and picture.animated:
                    url = picture.mp4
                    extension = 'mp4'
            x = Content(url, self.user, self.post_title, self.subreddit, file_name, "", '.' + extension, self.save_path,
                        self.subreddit_save_method, self.creation_date,  self.content_display_only)
            self.extracted_content.append(x)
        except NameError:
            self.logger.error('Failed direct extract: Unrecognized extension',
                              extra={'extractor_data': self.get_log_data()})
            self.failed_extract_messages.append("Failed: Unrecognized file extension: %s\nUser: %s  Subreddit: %s  "
                                                "Title: %s" % (self.url, self.user, self.subreddit, self.post_title))

    def extract_album(self):
        count = 1
        domain, album_id = self.url.rsplit('/', 1)
        for pic in self.client.get_album_images(album_id):
            url = pic.link
            address, extension = url.rsplit('.', 1)
            file_name = self.post_title if self.name_downloads_by == 'Post Title' else album_id
            if pic.type == 'image/gif' and pic.animated:
                extension = 'mp4'
                url = pic.mp4
            x = Content(url, self.user, self.post_title, self.subreddit, file_name + " ", count, '.' + extension,
                        self.save_path,self.subreddit_save_method, self.creation_date, self.content_display_only)
            count += 1
            self.extracted_content.append(x)

    def extract_single(self):
        domain, image_id = self.url.rsplit('/', 1)
        pic = self.client.get_image(image_id)
        url = pic.link
        address, extension = url.rsplit('.', 1)
        file_name = self.post_title if self.name_downloads_by == 'Post Title' else image_id
        if pic.type == 'image/gif' and pic.animated:
            extension = 'mp4'
            url = pic.mp4
        x = Content(url, self.user, self.post_title, self.subreddit, file_name, "", '.' + extension, self.save_path,
                    self.subreddit_save_method, self.creation_date, self.content_display_only)
        self.extracted_content.append(x)

    def extract_direct_mislinked(self):
        """
        All direct links to imgur.com must start with 'https://i.imgur.  Sometimes links get mis labeled somehow when
        they are posted.  This method is to add the correct address beginning to mislinked imgur urls and get a proper
        extraction
        """
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.gifv', '.mp4', '.webm']:
            if ext in self.url:
                index = self.url.find(ext)
                url = '%s%s' % (self.url[:index], ext)

        try:
            domain, id_with_ext = url.rsplit('/', 1)
            domain = 'https://i.imgur.com/'
            url = '%s%s' % (domain, id_with_ext)
            image_id, extension = id_with_ext.rsplit('.', 1)
            file_name = self.post_title if self.name_downloads_by == 'Post Title' else image_id
            if url.endswith('gifv') or url.endswith('gif'):
                picture = self.client.get_image(image_id)
                if picture.type == 'image/gif' and picture.animated:
                    url = picture.mp4
                    extension = 'mp4'
            x = Content(url, self.user, self.post_title, self.subreddit, file_name, "", '.' + extension, self.save_path,
                        self.subreddit_save_method, self.creation_date, self.content_display_only)
            self.extracted_content.append(x)
        except NameError:
            self.logger.error('Failed direct mislinked extract: Unrecognized extension',
                              extra={'extractor_data': self.get_log_data()})
            self.failed_extract_messages.append("Failed: Unrecognized file extension: %s\nUser: %s  Subreddit: %s  "
                                                "Title: %s" % (self.url, self.user, self.subreddit, self.post_title))


class GfycatExtractor(Extractor):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        """
        A subclass of the Extractor class.  This class interacts exclusively with the gfycat website through their api
        """
        super().__init__(url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                         save_path, content_display_only)
        self.api_caller = "https://gfycat.com/cajax/get/"

    def extract_content(self):
        """Dictates which extraction method should be used"""
        try:
            if self.url.lower().endswith(('webm', 'gif', 'gifv')):
                self.extract_direct_link()
            else:
                self.extract_single()
        except:
            self.extracted_content.append("Failed to locate the content at %s\nUser: %s  Subreddit: %s  Title: %s" %
                                          (self.url, self.user, self.subreddit, self.post_title))
            self.logger.error('Failed extract: Failed to locate content', extra={'extractor_data': self.get_log_data()})

    def extract_direct_link(self):
        domain, id_with_ext = self.url.rsplit('/', 1)
        gfy_id, ext = id_with_ext.rsplit('.', 1)
        file_name = self.post_title if self.name_downloads_by == 'Post Title' else gfy_id
        x = Content(self.url, self.user, self.post_title, self.subreddit, file_name, "", "." + ext, self.save_path,
                    self.subreddit_save_method, self.creation_date, self.content_display_only)
        self.extracted_content.append(x)

    def extract_single(self):
        domain, gif_id = self.url.rsplit('/', 1)
        gfy_json = self.get_json(self.api_caller + gif_id)
        gfy_url = gfy_json.get('gfyItem').get('webmUrl')
        file_name = self.post_title if self.name_downloads_by == 'Post Title' else gif_id
        x = Content(gfy_url, self.user, self.post_title, self.subreddit, file_name, "", '.webm', self.save_path,
                    self.subreddit_save_method, self.creation_date, self.content_display_only)
        self.extracted_content.append(x)


class VidbleExtractor(Extractor):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        """
        A sublcass of the Extractor class.  This class interacts exclusively with the Vidble website via BeautifulSoup4
        """
        super().__init__(url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                         save_path, content_display_only)
        self.vidble_base = "https://vidble.com"

    def extract_content(self):
        """Dictates which extraction method should be used"""
        try:
            if '/show/' in self.url or '/explore/' in self.url:
                self.extract_single()
            elif '/album/' in self.url:
                self.extract_album()
            elif self.url.lower().endswith(('.jpg', 'jpeg', '.png', '.gif', '.gifv', '.mp4', 'webm')):
                self.extract_direct_link()
            else:
                self.extract_album()  # If it hasn't found a match by here, try for album and hope it works
        except:
            self.extracted_content.append("Failed to locate the content at %s\nUser: %s  Subreddit: %s  Title: %s" %
                                          (self.url, self.user, self.subreddit, self.post_title))
            self.logger.error('Failed extract: Failed to locate content', extra={'extractor_data': self.get_log_data()})

    def extract_single(self):
        domain, vidble_id = self.url.rsplit('/', 1)
        if '.' in vidble_id:
            vidble_id = vidble_id[:vidble_id.rfind('.')]
        soup = BeautifulSoup(self.get_text(self.url), 'html.parser')
        imgs = soup.find_all('img')
        for img in imgs:
            img_class = img.get('class')
            if img_class is not None and img_class[0] == 'img2':
                link = img.get('src')
                if link is not None:
                    base, extension = link.rsplit('.', 1)
                    file_name = self.post_title if self.name_downloads_by == 'Post Title' else vidble_id
                    x = Content(self.vidble_base + link, self.user, self.post_title, self.subreddit, file_name, "",
                                '.' + extension, self.save_path, self.subreddit_save_method, self.creation_date,
                                self.content_display_only)
                    self.extracted_content.append(x)

    def extract_album(self):
        count = 1
        domain, vidble_id = self.url.rsplit('/', 1)
        soup = BeautifulSoup(self.get_text(self.url), 'html.parser')
        imgs = soup.find_all('img')
        for img in imgs:
            img_class = img.get('class')
            if img_class is not None and img_class[0] == 'img2':
                link = img.get('src')
                if link is not None:
                    base, extension = link.rsplit('.', 1)
                    file_name = self.post_title if self.name_downloads_by == 'Post Title' else vidble_id
                    x = Content(self.vidble_base + link, self.user, self.post_title, self.subreddit, file_name, count,
                                '.' + extension, self.save_path, self.subreddit_save_method, self.creation_date,
                                self.content_display_only)
                    self.extracted_content.append(x)
                    count += 1

    def extract_direct_link(self):
        domain, id_with_ext = self.url.rsplit('/', 1)
        vidble_id, extension = id_with_ext.rsplit('.', 1)
        file_name = self.post_title if self.name_downloads_by == 'Post Title' else vidble_id
        x = Content(self.url, self.user, self.post_title, self.subreddit, file_name, "", '.' + extension,
                    self.save_path, self.subreddit_save_method, self.creation_date, self.content_display_only)
        self.extracted_content.append(x)


class RedditUploadsExtractor(Extractor):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        """
        A subclass of the Extractor class.  This class interacts with reddit's own image hosting exclusively.

        At the time of this applications creation this extractor works decently, but is a very fragile extraction method
        and will likely often result in failed extractions. When an inevitable api is made public for this platform,
        this class will be updated to interact with it.
        """
        super().__init__(url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                         save_path, content_display_only)

    def extract_content(self):
        try:
            direct_link = "%s.jpg" % self.url
            x = Content(direct_link, self.user, self.post_title, self.subreddit, self.post_title, "", '.jpg',
                        self.save_path, self.subreddit_save_method, self.creation_date, self.content_display_only)
            self.extracted_content.append(x)
        except:
            self.extracted_content.append("Failed to locate the content at %s\nUser: %s  Subreddit: %s  Title: %s" %
                                          (self.url, self.user, self.subreddit, self.post_title))
            self.logger.error('Failed extract: Failed to locate content', extra={'extractor_data': self.get_log_data()})


class DirectExtractor(Extractor):

    def __init__(self, url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                 save_path, content_display_only):
        super().__init__(url, user, post_title, subreddit, creation_date, subreddit_save_method, name_downloads_by,
                         save_path, content_display_only)

    def extract_content(self):
        domain, id_with_ext = self.url.rsplit('/', 1)
        image_id, extension = id_with_ext.rsplit('.', 1)
        file_name = self.post_title if self.name_downloads_by == 'Post Title' else image_id
        x = Content(self.url, self.user, self.post_title, self.subreddit, file_name, "", '.' + extension,
                    self.save_path, self.subreddit_save_method, self.creation_date, self.content_display_only)
        self.extracted_content.append(x)
