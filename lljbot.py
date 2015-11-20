import webapp2
import urllib
import json
import HTMLParser
import os
import time
import textwrap
import logging
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

from secrets import token, admin_id, bot_id
url = 'https://api.telegram.org/bot' + token
url_send_message = url + '/sendMessage'
headers = {'Content-Type': 'application/json;charset=utf-8'}

class User(db.Model):
    username = db.StringProperty()
    first_name = db.StringProperty(multiline=True)
    last_name = db.StringProperty(multiline=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_received = db.DateTimeProperty(auto_now_add=True)
    last_sent = db.DateTimeProperty()
    last_auto = db.DateTimeProperty(default=datetime.fromtimestamp(0))
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

    def updateLastAuto(self):
        self.last_auto = datetime.now()
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

def sendMessage(uid, text, auto=False, force=False, markdown=False):
    if len(text) > 4096:
        sendLongMessage(uid, text, auto, force, markdown)
        return

    build = {
        'chat_id': uid,
        'text': text
    }

    if force:
        build['reply_markup'] = {'force_reply': True}
    if markdown:
        build['parse_mode'] = 'Markdown'

    data = json.dumps(build)

    try:
        result = urlfetch.fetch(url=url_send_message, payload=data, method=urlfetch.POST, headers=headers, deadline=3)
    except urlfetch_errors.Error as e:
        logging.warning('Error sending message to uid ' + str(uid))
        logging.warning(e)
        taskqueue.add(url='/message', payload=json.dumps({'auto': auto, 'data': data}))
        return

    response = json.loads(result.content)
    existing_user = getUser(uid)

    if response.get('ok') == True:
        logging.info('Message ' + str(response.get('result').get('message_id')) + ' sent to uid ' + str(uid))
        if existing_user:
            existing_user.updateLastSent()
            if auto:
                existing_user.updateLastAuto()
    else:
        logging.warning('Error sending message to uid ' + str(uid))
        logging.warning(result.content)
        if response.get('description') == '[Error]: Bot was kicked from a chat':
            if existing_user:
                existing_user.setActive(False)
        else:
            if response.get('description').startswith('[Error]: Bad Request: can\'t parse message text'):
                if build.get('parse_mode'):
                    del build['parse_mode']
                data = json.dumps(build)
            taskqueue.add(url='/message', payload=json.dumps({'auto': auto, 'data': data}))

def sendLongMessage(uid, text, auto, force=False, markdown=False):
    chunks = textwrap.wrap(text, width=4096, replace_whitespace=False, drop_whitespace=False)
    for chunk in chunks:
        sendMessage(uid, chunk, auto, force, markdown)

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

    remote_error = 'Sorry, I\'m having some difficulty accessing the LLJ website. Please try again later.'

    feedback_string = 'Please reply with your feedback. I will relay the message to my developer.'

    def post(self):
        data = json.loads(self.request.body)
        logging.info(self.request.body)

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
        name = first_name.encode('utf-8', 'ignore').strip()

        actual_id = data.get('message').get('from').get('id')
        actual_username = data.get('message').get('from').get('username')
        if actual_username:
            actual_username = actual_username.encode('utf-8', 'ignore').strip()
        actual_name = data.get('message').get('from').get('first_name').encode('utf-8', 'ignore').strip()
        actual_last_name = data.get('message').get('from').get('last_name')
        if actual_last_name:
            actual_last_name = actual_last_name.encode('utf-8', 'ignore').strip()

        text = data.get('message').get('text')
        if text:
            text = text.encode('utf-8', 'ignore')

        reply_to_message = data.get('message').get('reply_to_message')

        if reply_to_message:
            if str(reply_to_message.get('from').get('id')) == bot_id and reply_to_message.get('text') == self.feedback_string:
                name_string = actual_name
                if actual_last_name:
                    name_string += ' ' + actual_last_name
                if actual_username:
                    name_string += ' @' + actual_username

                if user.isGroup():
                    message_to_dev = 'Feedback from {} ({}) via group {} ({}):\n{}'.format(name_string, actual_id, name, id, text)
                else:
                    message_to_dev = 'Feedback from {} ({}):\n{}'.format(name_string, actual_id, text)

                sendMessage(admin_id, message_to_dev)
                sendMessage(id, 'Your message has been sent to my developer. Thanks for your feedback, {}!'.format(actual_name))
                return

        if user.last_sent == None or text == '/start':
            if user.last_sent == None:
                new_user = True
            else:
                new_user = False

            if not user.isActive():
                user.setActive(True)

            if user.isGroup():
                response = 'Hello, friends in ' + name + '! Thanks for adding me in! This group chat is now subscribed.'
            else:
                response = 'Hello, ' + name + '! Welcome! You are now subscribed.'
            response += ' You may enter one of the following commands:' + self.command_list_unsub
            response += '\n\nIn the meantime, here\'s today\'s material to get you started!'
            sendMessage(id, response)

            response = getDevo()
            if response == None:
                response = self.remote_error
            sendMessage(id, response, markdown=True)

            if new_user:
                new_alert = 'New user: ' + name
                if last_name:
                    new_alert += ' ' + actual_last_name
                if username:
                    new_alert += ' @' + actual_username
                sendMessage(admin_id, new_alert)

            return

        if text == None:
            return

        command = text.lower().strip()
        short_cmd = ''.join(command.split())

        if command == '/subscribe' or short_cmd.startswith(('/subscribe@lljbot', '@lljbot/subscribe')):
            if user.isActive():
                response = 'Looks like you are already subscribed!'
            else:
                user.setActive(True)
                response = 'Success!'
            response += ' You will receive material every day at midnight, Singapore time :)'

        elif command == '/unsubscribe' or short_cmd.startswith(('/unsubscribe@lljbot', '@lljbot/unsubscribe')):
            if not user.isActive():
                response = 'Looks like you already unsubscribed! ' + \
                           'Don\'t worry; you won\'t be receiving any more automatic updates.'
            else:
                user.setActive(False)
                response = 'You have successfully unsubscribed and will ' + \
                           'no longer receive automatic updates. Use /subscribe if this was a mistake.'
            response += ' You can still get material manually by using the commands :)'

        elif command == '/today' or short_cmd.startswith(('/today@lljbot', '@lljbot/today')):
            response = getDevo()

        elif command == '/yesterday' or short_cmd.startswith(('/yesterday@lljbot', '@lljbot/yesterday')):
            response = getDevo(-1)

        elif command == '/tomorrow' or short_cmd.startswith(('/tomorrow@lljbot', '@lljbot/tomorrow')):
            response = getDevo(1)

        elif command == '/feedback' or short_cmd.startswith(('/feedback@lljbot', '@lljbot/feedback')):
            response = self.feedback_string
            sendMessage(id, response, force=True)
            return

        else:
            if user.isGroup() and '@lljbot' not in command:
                return

            if user.isGroup():
                name = actual_name

            response = 'Sorry ' + name + ', I couldn\'t understand that. ' + \
                       'Please enter one of the following commands:'
            if user.isActive():
                response += self.command_list_unsub
            else:
                response += self.command_list_sub

            sendMessage(id, response)
            return

        if response ==  None:
            response = self.remote_error

        sendMessage(id, response, markdown=True)

class SendPage(webapp2.RequestHandler):
    def get(self):
        today = (datetime.utcnow() + timedelta(hours=8)).date()
        today_time = datetime(today.year, today.month, today.day) - timedelta(hours=8)

        query = User.all()
        query.filter('active =', True)
        query.filter('last_auto <', today_time)

        devo = getDevo()
        if devo:
            try:
                for user_key in query.run(keys_only=True, batch_size=1000):
                    sendMessage(user_key.name(), devo, auto=True, markdown=True)
            except db.Error as e:
                taskqueue.add(url='/retry')
        else:
            taskqueue.add(url='/retry')

class RetryPage(webapp2.RequestHandler):
    def post(self):
        today = (datetime.utcnow() + timedelta(hours=8)).date()
        today_time = datetime(today.year, today.month, today.day) - timedelta(hours=8)

        query = User.all()
        query.filter('active =', True)
        query.filter('last_auto <', today_time)

        devo = getDevo()
        if devo:
            for user_key in query.run(keys_only=True, batch_size=1000):
                sendMessage(user_key.name(), devo, auto=True, markdown=True)
        else:
            self.abort(502)

class MessagePage(webapp2.RequestHandler):
    def post(self):
        params = json.loads(self.request.body)
        auto = params.get('auto')
        data = params.get('data')
        uid = json.loads(data).get('chat_id')

        logging.info('auto = ' + str(auto))
        logging.info(data)

        try:
            result = urlfetch.fetch(url=url_send_message, payload=data, method=urlfetch.POST, headers=headers, deadline=3)
        except urlfetch_errors.Error as e:
            logging.warning('Error sending message to uid ' + str(uid))
            logging.warning(e)
            self.abort(502)

        response = json.loads(result.content)
        existing_user = getUser(uid)

        if response.get('ok') == True:
            logging.info('Message ' + str(response.get('result').get('message_id')) + ' sent to uid ' + str(uid))
            if existing_user:
                existing_user.updateLastSent()
                if auto:
                    existing_user.updateLastAuto()
        else:
            logging.warning('Error sending message to uid ' + str(uid))
            logging.warning(result.content)
            if response.get('description') == '[Error]: Bot was kicked from a chat':
                if existing_user:
                    existing_user.setActive(False)
            else:
                self.abort(502)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + token, LljPage),
    ('/send', SendPage),
    ('/retry', RetryPage),
    ('/message', MessagePage),
], debug=True)