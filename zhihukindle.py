from datetime import date, timedelta
from shutil import copy
from os import path, listdir, system
from jinja2 import Environment, PackageLoader
import sys
import json
import urllib2
import hashlib
import re
import os
import logging
import threading
import Queue

from bs4 import BeautifulSoup
from lib import escape
from PIL import Image
from config import TIMEZONE, OUTPUT_DIR

imgq = Queue.Queue(0)

reload(sys)
sys.setdefaultencoding('utf8')

templates_env = Environment(loader=PackageLoader('zhihukindle', 'templates_zhihu'))
ROOT = path.dirname(path.abspath(__file__))

iswindows = 'win23' in sys.platform.lower() or 'win64' in sys.platform.lower()
isosx = 'darvim' in sys.platform.lower()
isfreebsd = 'freebsd' in sys.platform.lower()
islinux = not(iswindows or isosx or isfreebsd)


def build(feed, output_dir):
    # Parse the feeds and grave useful information to build a structure
    # which will be passed to the templates.
    data = []

    # # Initialize some counters for the TOC IDs.
    ## We start counting at 2 because 1 is the TOC itself.
    feed_number = 1
    play_order = 1

    feed_number += 1
    play_order += 1
    local = {
        'number': feed_number,
        'play_order': play_order,
        'entries': [],
        'title': "Zhihu Daliy " + feed['display_date'].decode('utf-8'),
    }

    entry_number = 0
    for entry in feed['news']:
        play_order += 1
        entry_number += 1

        local_entry = {
            'number': entry_number,
            'play_order': play_order,
            'title': entry['title'],
            'content': entry['content'],
        }

        local['entries'].append(local_entry)

    data.append(local)

    # Wrap data and today's date in a dict to use the magic of **.
    wrap = {
        'date': (date.today() + timedelta(hours = TIMEZONE)).isoformat(),
        'feeds': data,
    }

    # Render and output templates

    ## TOC (NCX)
    render_and_write('toc.xml', wrap, 'toc.ncx', output_dir)
    ## TOC (HTML)
    render_and_write('toc.html', wrap, 'toc.html', output_dir)
    ## OPF
    render_and_write('opf.xml', wrap, 'daily.opf', output_dir)
    ## Content
    for feed in data:
        render_and_write('feed.html', feed, '%s.html' % feed['number'], output_dir)

    # Copy the assets
    for name in listdir(path.join(ROOT, 'assets')):
        copy(path.join(ROOT, 'assets', name), path.join(output_dir, name))


def parser_zhihu():
    """Parse Zhihu Daily API to JSON data"""
    today = (date.today() + timedelta(hours = TIMEZONE)).strftime("%Y%m%d")
    api_url = 'http://news.at.zhihu.com/api/1.2/news/before/' + today
    print(api_url)
    daily_data = request(api_url, "")
    news = daily_data['news']
    for new in news:
        new['content'] = request(new['url'], api_url)['body']
    return daily_data


def request(url, request_url):
    """Resuest urls with headers"""
    header = {
        'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6',
        'Referer': request_url,
    }
    req = urllib2.Request(
        url=url.encode('utf-8'),
        headers=header
    )
    opener = urllib2.build_opener()
    response = opener.open(req, timeout=30)
    return json.loads(response.read())

def buildZhihu(output_dir):
    global imgq
    data = parser_zhihu()
    images = []
    for new in data['news']:
        soup = BeautifulSoup(new['content'])
        for img in list(soup.find_all('img')):
            if img['src'].encode('utf-8').lower().endswith('jpg'):
                localimg, fullimg = parse_image(output_dir, img['src'])
                if os.path.isfile(fullimg) is False:
                    images.append({
                        'url': img['src'],
                        'filename': fullimg,
                        'referer': new['share_url'],
                    })
                if localimg:
                    img['src'] = localimg
        new['content'] = soup.div.__str__()
    for k in images:
        imgq.put(k)
    imgthreads = []
    for i in range(4):
        t = ImageDownloader('Threadimg %s' % (i + 1))
        imgthreads.append(t)
    for t in imgthreads:
        t.setDaemon(True)
        t.start()
    imgq.join()

    build(data, output_dir)


def render_and_write(template_name, context, output_name, output_dir):
    """Render `template_name` with `context` and write the result in the file
    `output_dir`/`output_name`."""

    template = templates_env.get_template(template_name)
    f = open(path.join(output_dir, output_name), "w")
    f.write(template.render(**context))
    f.close()


def mobi(input_file, exec_path):
    """Execute the KindleGen binary to create a MOBI file."""
    system("%s %s" % (exec_path, input_file))


def parse_image(output_dir, url, filename=None):
    url = escape.utf8(url)
    image_guid = hashlib.sha1(url).hexdigest()

    x = url.split('.')
    ext = 'jpg'
    if len(x) > 1:
        ext = x[-1]

        if len(ext) > 4:
            ext = ext[0:3]

        ext = re.sub('[^a-zA-Z]', '', ext)
        ext = ext.lower()

        if ext not in ['jpg', 'jpeg', 'gif', 'png', 'bmp']:
            ext = 'jpg'

    filename = image_guid + '.' + ext

    img_dir = output_dir + '/images'
    fullname = img_dir + '/' + filename

    if not os.path.exists(img_dir):
        os.makedirs(img_dir)

    localimage = 'images/%s' % filename
    return localimage, fullname


class ImageDownloader(threading.Thread):
    def __init__(self, threadname):
        threading.Thread.__init__(self, name=threadname)

    def run(self):
        global imgq

        while True:
            i = imgq.get()
            self.getimage(i)
            imgq.task_done()

    def getimage(self, i, retires=1):
        try:
            header = {
                'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.6) Gecko/20091201 Firefox/3.5.6',
                'Referer': i['referer']
            }
            req = urllib2.Request(
                url=i['url'].encode('utf-8'),
                headers=header
            )
            opener = urllib2.build_opener()
            response = opener.open(req, timeout=30)
            with open(i['filename'], 'wb') as img:
                img.write(response.read())
            if Image:
                try:
                    img = Image.open(i['filename'])
                    # width, height = img1.size
                    # print(width, height)
                    # img = img1
                    # if height > 400:
                    #     ratio = float(400 / height)
                    #     img = img1.resize((int(ratio * width), 400))
                    # print(img.size)
                    new_img = img.convert("L")
                    new_img.save(i['filename'])
                except Exception, e:
                    print(e)
            logging.info("download: {}".format(i['url'].encode('utf-8')))
        except urllib2.HTTPError as http_err:
            if retires > 0:
                return self.getimage(i, retires - 1)
            logging.info("HttpError: {},{}".format(http_err, i['url'].encode('utf-8')))
        except Exception, e:
            if retires > 0:
                return self.getimage(i, retires - 1)
            logging.error("Failed: {}".format(e, i['url'].encode('utf-8')))


def main():
    print("Running ZhihuKindle...")
    print("-> Generating files...")
    base_dir = os.path.split(os.path.realpath(__file__))[0]
    output_dir = path.join(base_dir, OUTPUT_DIR)
    buildZhihu(output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("-> Build the MOBI file using KindleGen...")
    kindlegen = ""
    if iswindows:
        kindlegen = "kindlegen.exe"
    elif islinux:
        kindlegen = "kindlegen"
    else:
        kindlegen = "kindlegen"

    mobi(path.join(output_dir, 'daily.opf'), path.join(base_dir, kindlegen))
    print("Done")


if __name__ == "__main__":
    from sys import argv, exit

    def usage():
        print("""KindWave usage: python zhihukindle.py""")

    if not len(argv) > 0:
        usage()
        exit(64)
    else:
        main()
