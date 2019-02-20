"""
Download the latest phantomjs linux binary from the http://phantomjs.org/download.html download page
"""
import re
import sys
import shutil
import tarfile
import logging
from io import BytesIO
from distutils.version import StrictVersion
from pathlib import Path
from urllib.request import urlopen, Request

from bs4 import BeautifulSoup


PHANTOMJS_BINARY_DOWNLOAD_PAGE_URL = 'http://phantomjs.org/download.html'
DEFAULT_LOCAL_BIN_DIRECTORY = Path(__file__).absolute().parent / 'bin'


logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(funcName)s: %(message)s'
)
logger = logging.getLogger(__name__)


class PhantomJSBinaryDownloader:

    def __init__(self, phantomjs_binary_download_page_url: str = PHANTOMJS_BINARY_DOWNLOAD_PAGE_URL, local_bin_directory: Path = DEFAULT_LOCAL_BIN_DIRECTORY):
        self.url = phantomjs_binary_download_page_url

        local_bin_directory.mkdir(exist_ok=True)
        self.local_bin_directory = local_bin_directory.absolute()
        self._page_soup = None

    def _process_tarfile(self, source_fileobj):
        """
        Extract the binary 'phantomjs' file from the tar file
        """
        output_filepath = None
        tar = tarfile.open(fileobj=source_fileobj, mode='r:*')
        for member in tar.getmembers():
            if member.name.endswith('phantomjs'):
                logger.info(f'Extracting ({member.name}) to ({self.local_bin_directory}) ...')
                tar.extract(member, path=self.local_bin_directory)
                temp_output_filepath = self.local_bin_directory / member.name
                output_filepath = self.local_bin_directory / 'phantomjs'
                shutil.move(str(temp_output_filepath), str(output_filepath))
                # remove empty directory
                temp_output_directory = temp_output_filepath.parent
                while temp_output_directory != self.local_bin_directory:
                    logger.debug(f'Removing Directory ({temp_output_directory}) ...')
                    temp_output_directory.rmdir()  # delete
                    temp_output_directory = temp_output_directory.parent
                break
        return output_filepath

    def download(self):
        self.get_page()
        version, filename, download_url = self.get_latest_version_download_url()
        assert filename.endswith(('.tar.bz2', '.tar.xz'))

        # prepare request with
        chrome_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
        headers = {'User-agent': chrome_user_agent}
        request = Request(download_url, headers=headers)

        temp_fileobj = BytesIO()
        logger.info(f'Downloading ({download_url}) ...')
        with urlopen(request) as binary:
            content_length = int(binary.getheader('content-length'))
            logger.debug(f'content-length: {content_length}')
            blocksize = max(4096, content_length // 10)

            data = binary.read(blocksize)
            size = len(data)
            while data:
                temp_fileobj.write(data)
                data = binary.read(blocksize)
                size += len(data)
                percentage = (size / content_length) * 100
                logger.debug(f'{percentage:.2f}%')
            logger.info('Download Complete!')

        temp_fileobj.seek(0)  # reset to start of file
        output_filepath = self._process_tarfile(temp_fileobj)

        if not output_filepath:
            logger.error(f'"phantomjs" not found in tar!')
        version_identifier = self.local_bin_directory / version
        version_identifier.open('w')
        return output_filepath

    def get_latest_version_download_url(self):
        assert self._page_soup

        pattern = r'phantomjs-(\d+\.\d+\.\d+)-linux-x86_64.tar.(bz2|xz)'
        linux_versions = {}
        for link in self._page_soup.find_all('a'):
            m = re.match(pattern, link.text)
            if m:
                version = m.groups()[0]
                filename = link.text
                file_url = link.get('href')
                linux_versions[version] = (filename, file_url)
                logger.info(f'Found version ({version}): {filename} [{file_url}]')

        max_version = max(linux_versions.keys(), key=StrictVersion)
        filename, url = linux_versions[max_version]
        return max_version, filename, url

    def get_page(self):
        logger.info(f'Collecting page source ({self.url}) ...')
        with urlopen(self.url) as connection:
            self._page_soup = BeautifulSoup(connection, features='html.parser')


if __name__ == '__main__':
    downloader = PhantomJSBinaryDownloader()
    output_filepath = downloader.download()
    logger.info(f'phantomjs binary successfully downloaded and extracted to: {output_filepath}')
