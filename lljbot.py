import webapp2
import urllib
import json
import HTMLParser
import os
import time
import textwrap
from google.appengine.api import urlfetch, urlfetch_errors, taskqueue
from google.appengine.ext import db
from datetime import datetime, timedelta

def getDevo(delta=0):
    date = (datetime.utcnow() + timedelta(hours=8, days=delta)).strftime('%Y-%m-%d')
    devo_url = 'http://www.duranno.com/livinglife/qt/reload_default.asp?OD=' + date

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
            result += num + ' ' + strip_markdown(text) + '\n'
            str = str[end:]
        return result.strip()

    def strip_markdown(str):
        return str.replace('*', ' ').replace('_', ' ')

    def get_remote_date(content):
        start = content.find('var videoNowDate = "') + 20
        return content[start:start + 10]

    if delta != 0 and get_remote_date(content) != date:
        if (delta == -1):
            return 'Sorry, the LLJ website is no longer hosting yesterday\'s material.'
        else:
            return 'Sorry, the LLJ website hasn\'t made tomorrow\'s material available yet.'

    title_start = content.find('<!-- today QT -->')
    title_end = content.find('<!-- bible words -->')
    title = format(content[title_start:title_end])
    start = title.find('<div class="today_m">') + 21
    end = title.find('</div>', start)
    date = strip_markdown(format(title[start:end]))
    start = title.find('<div class="title">') + 59
    end = title.find('</a>', start)
    heading = strip_markdown(format(title[start:end]))
    start = title.find('<div class="sub_title">') + 23
    end = title.find('</div>', start)
    verse = strip_markdown(format(title[start:end]))

    passage_start = title_end
    passage_end = content.find('<!-- Reflection-->')
    passage = format_passage(content[passage_start:passage_end])

    reflection_start = passage_end
    reflection_end = content.find('<!--  Letter to God -->')
    reflection = content[reflection_start:reflection_end]
    start = reflection.find('<div class="con">') + 17
    end = reflection.find('</div>', start)
    reflection = strip_markdown(format(reflection[start:end]))

    prayer_start = reflection_end
    prayer_end = content.find('<!-- Share SNS -->')
    prayer = content[prayer_start:prayer_end]
    start = prayer.find('<div class="con" style="padding-top:25px;">') + 43
    end = prayer.find('</div>', start)
    prayer = strip_markdown(format(prayer[start:end]))

    daynames = ['Yesterday\'s', 'Today\'s', 'Tomorrow\'s']

    devo = u'\U0001F4C5' + ' ' + daynames[delta + 1] + ' QT - _' + date + '_\n\n' + \
           '*' + heading + '*\n' + verse + '\n\n' + \
           u'\U0001F4D9' + ' *Scripture* _(NIV)_\n\n' + passage + '\n\n' + \
           u'\U0001F4DD' + ' *Reflection*\n\n' + reflection + '\n\n' + \
           u'\U0001F64F' + ' *Prayer*\n\n' + prayer
    return devo

from secrets import token
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

    def isGroup(self):
        return int(self.key().name()) < 0

    def isActive(self):
        return self.active

    def setActive(self, active):
        self.active = active
        self.put()

    def updateLastReceived(self):
        self.last_received = datetime.now()
        self.put()

    def updateLastSent(self):
        self.last_sent = datetime.now()
        self.put()

def getUser(uid):
    key = db.Key.from_path('User', str(uid))
    return db.get(key)

def updateProfile(uid, uname, fname, lname):
    existing_user = getUser(uid)
    if existing_user:
        existing_user.username = uname
        existing_user.first_name = fname
        existing_user.last_name = lname
        existing_user.updateLastReceived()
        #existing_user.put()
        return existing_user
    else:
        user = User(key_name=str(uid), username=uname, first_name=fname, last_name=lname)
        user.put()
        return user

def sendMessage(uid, text):
    if len(text) > 4096:
        sendLongMessage(uid, text)
        return

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

    existing_user = getUser(uid)
    if existing_user:
        existing_user.updateLastSent()

def sendLongMessage(uid, text):
    chunks = textwrap.wrap(text, width=4096, replace_whitespace=False, drop_whitespace=False)
    for chunk in chunks:
        sendMessage(uid, chunk)

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('LLJBot backend running...\n')

class LljPage(webapp2.RequestHandler):
    command_list = '\n\n' + \
                   '/today - get today\'s material\n' + \
                   '/yesterday - get yesterday\'s material\n' + \
                   '/tomorrow - get tomorrow\'s material'

    command_unsub = '\n/unsubscribe - disable automatic updates'
    command_sub = '\n/subscribe - re-enable automatic updates'

    command_list_unsub = command_list + command_unsub
    command_list_sub = command_list + command_sub

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
        user = updateProfile(id, username, first_name, last_name)

        if user.last_sent == None:
            if user.isGroup():
                response = 'Hello, friends in' + first_name.strip() + '! Welcome! This group chat is now subscribed.'
            else:
                response = 'Hello, ' + first_name.strip() + '! Welcome! You are now subscribed.'
            response += ' To get started, enter one of the following commands:' + self.command_list_unsub
            sendMessage(id, response)
            return

        command = data.get('message').get('text')
        if command == None:
            return

        command = command.lower().strip()
        if command == '/subscribe' or command == '/subscribe@LljBot':
            if user.isActive():
                response = 'Looks like you are already subscribed!'
            else:
                user.setActive(True)
                response = 'Success!'
            response += ' You will receive material every day at midnight, Singapore time :)'

        elif command == '/unsubscribe' or command == '/unsubscribe@LljBot':
            if not user.isActive():
                response = 'Looks like you already unsubscribed! ' + \
                           'Don\'t worry; you won\'t be receiving any more automatic updates.'
            else:
                user.setActive(False)
                response = 'Success! You will no longer receive automatic updates.'
            response += ' You can still get material manually by using the commands :)'

        elif command == '/today' or command == '/today@lljbot':
            response = getDevo()
        elif command == '/yesterday' or command == '/yesterday@lljbot':
            response = getDevo(-1)
        elif command == '/tomorrow' or command == '/tomorrow@lljbot':
            response = getDevo(1)
        else:
            if user.isGroup() and '@lljbot' not in command:
                return

            if user.isGroup():
                name = data.get('message').get('from').get('first_name')
            else:
                name = first_name

            response = 'Sorry ' + name.strip() + ', I couldn\'t understand that. ' + \
                       'Please enter one of the following commands:'
            if user.isActive():
                response += self.command_list_unsub
            else:
                response += self.command_list_sub

        if response ==  None:
            response = 'Sorry, I\'m having some difficulty accessing the LLJ website. Please try again later.'

        sendMessage(id, response)

class SendPage(webapp2.RequestHandler):
    def get(self):
        query = User.all()
        query.filter('active =', True)
        devo = getDevo()
        if devo:
            for user_key in query.run(keys_only=True):
                sendMessage(user_key.name(), devo)
        else:
            taskqueue.add(url='/retry')

class RetryPage(webapp2.RequestHandler):
    def post(self):
        query = User.all()
        query.filter('active =', True)
        devo = getDevo()
        if devo:
            for user_key in query.run(keys_only=True):
                sendMessage(user_key.name(), devo)
        else:
            self.abort(502)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + token, LljPage),
    ('/send', SendPage),
    ('/retry', RetryPage),
], debug=True)