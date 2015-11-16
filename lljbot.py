import webapp2
import urllib
import json
import HTMLParser
import os
import time
from google.appengine.api import urlfetch, urlfetch_errors, taskqueue
from google.appengine.ext import db
from datetime import datetime

def getDevo():
    devo_url = 'http://www.duranno.com/livinglife/qt/reload_default.asp'

    try:
        result = urlfetch.fetch(devo_url, deadline=10)
    except urlfetch_errors.Error as e:
        return None

    content = result.content.decode('cp949', 'ignore')

    h = HTMLParser.HTMLParser()

    def format(str):
        str = str.replace('<br>', '\n')
        return h.unescape(str).strip()

    def format_passage(str):
        result = ''
        first = str.find('<!-- bible verse and text -->')
        str = str[first:]
        while '<!-- bible verse and text -->' in str:
            start = str.find('<div class="listTxt">') + 21
            end = str.find('</div>', start)
            num = '_' + format(str[start:end]) + '_'
            start = str.find('<div class="listCon">') + 21
            end = str.find('</div>', start)
            text = format(str[start:end])
            result += num + ' ' + text + '\n'
            str = str[end:]
        return result.strip()

    title_start = content.find('<!-- today QT -->')
    title_end = content.find('<!-- bible words -->')
    title = format(content[title_start:title_end])
    start = title.find('<div class="today_m">') + 21
    end = title.find('</div>', start)
    date = format(title[start:end])
    start = title.find('<div class="title">') + 59
    end = title.find('</a>', start)
    heading = format(title[start:end])
    start = title.find('<div class="sub_title">') + 23
    end = title.find('</div>', start)
    verse = format(title[start:end])

    passage_start = title_end
    passage_end = content.find('<!-- Reflection-->')
    passage = format_passage(content[passage_start:passage_end])

    reflection_start = passage_end
    reflection_end = content.find('<!--  Letter to God -->')
    reflection = content[reflection_start:reflection_end]
    start = reflection.find('<div class="con">') + 17
    end = reflection.find('</div>', start)
    reflection = format(reflection[start:end])

    prayer_start = reflection_end
    prayer_end = content.find('<!-- Share SNS -->')
    prayer = content[prayer_start:prayer_end]
    start = prayer.find('<div class="con" style="padding-top:25px;">') + 43
    end = prayer.find('</div>', start)
    prayer = format(prayer[start:end])

    devo = u'\U0001F4C5' + ' Today\'s QT - _' + date + '_\n\n*' + heading + '*\n' + verse + '\n\n' + \
           u'\U0001F4D9' + ' *Scripture* _(NIV)_\n\n' + passage + '\n\n' + \
           u'\U0001F4DD' + ' *Reflection*\n\n' + reflection + '\n\n' + \
           u'\U0001F64F' + ' *Prayer*\n\n' + prayer
    return devo

token = os.environ.get('TELEGRAM_BOT_TOKEN')
url = 'https://api.telegram.org/bot' + token
url_send_message = url + '/sendMessage'
headers = {'Content-Type': 'application/json;charset=utf-8'}

class User(db.Model):
    username = db.StringProperty()
    first_name = db.StringProperty()
    last_name = db.StringProperty()
    created = db.DateTimeProperty(auto_now_add=True)
    last_received = db.DateTimeProperty(auto_now_add=True)
    last_sent = db.DateTimeProperty()
    active = db.BooleanProperty(default=True)

def update(uid, uname, fname, lname):
    key = db.Key.from_path('User', str(uid))
    existing_user = db.get(key)
    if existing_user:
        existing_user.username = uname
        existing_user.first_name = fname
        existing_user.last_name = lname
        existing_user.last_received = datetime.now()
        existing_user.active = True
        existing_user.put()
    else:
        user = User(key_name=str(uid), username=uname, first_name=fname, last_name=lname)
        user.put()

def sendMessage(uid, text):
    key = db.Key.from_path('User', str(uid))
    existing_user = db.get(key)
    if existing_user:
        existing_user.last_sent = datetime.now()
        existing_user.put()
    data = {
        'chat_id': uid,
        'text': text,
        'parse_mode': 'Markdown'
    }
    result = urlfetch.fetch(url=url_send_message, payload=json.dumps(data), method=urlfetch.POST, headers=headers)
    response = json.loads(result.content)
    if response.get('ok') == False:
        if response.get('description') == '[Error]: Bot was kicked from a chat':
            if existing_user:
                existing_user.active = False
                existing_user.put()
        else:
            time.sleep(1)
            urlfetch.fetch(url=url_send_message, payload=json.dumps(data), method=urlfetch.POST, headers=headers)

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('LLJBot backend running...\n')

class LljPage(webapp2.RequestHandler):
    def post(self):
        data = json.loads(self.request.body)
        if data.get('message').get('chat').get('type') == 'private':
            id = data.get('message').get('from').get('id')
            username = data.get('message').get('from').get('username')
            first_name = data.get('message').get('from').get('first_name')
            last_name = data.get('message').get('from').get('last_name')
        else:
            id = data.get('message').get('chat').get('id')
            username = None
            first_name = data.get('message').get('chat').get('title')
            last_name = None
        update(id, username, first_name, last_name)
        devo = getDevo()
        if devo ==  None:
            devo = 'Sorry, I\'m having some difficulty accessing the LLJ website. Please try again later.'
        sendMessage(id, devo)

class EnqueuePage(webapp2.RequestHandler):
    def get(self):
        taskqueue.add(url='/send')

class SendPage(webapp2.RequestHandler):
    def post(self):
        query = User.all()
        query.filter('active =', True)
        devo = getDevo()
        if devo ==  None:
            self.abort(502)
        for user in query.run(keys_only=True):
            sendMessage(user.name(), devo)
            time.sleep(0.0333)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + token, LljPage),
    ('/enqueue', EnqueuePage),
    ('/send', SendPage),
], debug=True)