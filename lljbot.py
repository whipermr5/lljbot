import webapp2
import logging
import json
import HTMLParser
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

    def prep_str(string):
        string = string.replace('<br>', '\n')
        return h.unescape(string).strip()

    def prep_passage(string):
        result = ''
        first = string.find('<!-- bible verse and text -->')
        string = string[first:]
        while '<!-- bible verse and text -->' in string:
            start = string.find('<div class="listTxt">') + 21
            end = string.find('</div>', start)
            num = '_' + prep_str(string[start:end]) + '_'
            start = string.find('<div class="listCon">') + 21
            end = string.find('</div>', start)
            text = prep_str(string[start:end])
            result += num + ' ' + strip_markdown(text) + '\n'
            string = string[end:]
        return result.strip()

    def strip_markdown(string):
        return string.replace('*', ' ').replace('_', ' ')

    def get_remote_date(content):
        start = content.find('var videoNowDate = "') + 20
        return content[start:start + 10]

    if delta != 0 and get_remote_date(content) != date:
        if delta == -1:
            return 'Sorry, the LLJ website is no longer hosting yesterday\'s material.'
        else:
            return 'Sorry, the LLJ website hasn\'t made tomorrow\'s material available yet.'

    title_start = content.find('<!-- today QT -->')
    title_end = content.find('<!-- bible words -->')
    title = prep_str(content[title_start:title_end])
    start = title.find('<div class="today_m">') + 21
    end = title.find('</div>', start)
    date = strip_markdown(prep_str(title[start:end]))
    start = title.find('<div class="title">') + 59
    end = title.find('</a>', start)
    heading = strip_markdown(prep_str(title[start:end]))
    start = title.find('<div class="sub_title">') + 23
    end = title.find('</div>', start)
    verse = strip_markdown(prep_str(title[start:end]))

    passage_start = title_end
    passage_end = content.find('<!-- Reflection-->')
    passage = prep_passage(content[passage_start:passage_end])

    reflection_start = passage_end
    reflection_end = content.find('<!--  Letter to God -->')
    reflection = content[reflection_start:reflection_end]
    start = reflection.find('<div class="con">') + 17
    end = reflection.find('</div>', start)
    reflection = strip_markdown(prep_str(reflection[start:end]))

    prayer_start = reflection_end
    prayer_end = content.find('<!-- Share SNS -->')
    prayer = content[prayer_start:prayer_end]
    start = prayer.find('<div class="con" style="padding-top:25px;">') + 43
    end = prayer.find('</div>', start)
    prayer = strip_markdown(prep_str(prayer[start:end]))

    daynames = ['Yesterday\'s', 'Today\'s', 'Tomorrow\'s']

    devo = u'\U0001F4C5' + ' ' + daynames[delta + 1] + ' QT - _' + date + '_\n\n' + \
           '*' + heading + '*\n' + verse + '\n\n' + \
           u'\U0001F4D9' + ' *Scripture* _(NIV)_\n\n' + passage + '\n\n' + \
           u'\U0001F4DD' + ' *Reflection*\n\n' + reflection + '\n\n' + \
           u'\U0001F64F' + ' *Prayer*\n\n' + prayer
    return devo

from secrets import token, admin_id, bot_id
telegram_url = 'https://api.telegram.org/bot' + token
telegram_url_send = telegram_url + '/sendMessage'
json_header = {'Content-Type': 'application/json;charset=utf-8'}

def telegramPost(data):
    return urlfetch.fetch(url=telegram_url_send, payload=data, method=urlfetch.POST,
                          headers=json_header, deadline=3)

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
        chunks = textwrap.wrap(text, width=4096, replace_whitespace=False, drop_whitespace=False)
        for chunk in chunks:
            sendMessage(uid, chunk, auto, force, markdown)
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
        result = telegramPost(data)
    except urlfetch_errors.Error as e:
        logging.warning('Error sending message to uid ' + str(uid) + ':\n' + str(e))
        taskqueue.add(url='/message', payload=json.dumps({'auto': auto, 'data': data}))
        return

    response = json.loads(result.content)
    existing_user = getUser(uid)

    if response.get('ok') == True:
        msg_id = response.get('result').get('message_id')
        logging.info('Message ' + str(msg_id)  + ' sent to uid ' + str(uid))
        if existing_user:
            existing_user.updateLastSent()
            if auto:
                existing_user.updateLastAuto()
    else:
        error_description = response.get('description')
        if error_description == '[Error]: Bot was kicked from a chat':
            logging.info('Bot was kicked from uid ' + str(uid))
            if existing_user:
                existing_user.setActive(False)
        else:
            logging.warning('Error sending message to uid ' + str(uid) + ':\n' + result.content)
            if error_description.startswith('[Error]: Bad Request: can\'t parse message text'):
                if build.get('parse_mode'):
                    del build['parse_mode']
                data = json.dumps(build)
            taskqueue.add(url='/message', payload=json.dumps({'auto': auto, 'data': data}))

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('LLJBot backend running...\n')

class LljPage(webapp2.RequestHandler):
    cmd_list = '\n\n' + \
                   '/today - get today\'s material\n' + \
                   '/yesterday - get yesterday\'s material\n' + \
                   '/tomorrow - get tomorrow\'s material'
    cmd_unsub = '\n/unsubscribe - disable automatic updates'
    cmd_sub = '\n/subscribe - re-enable automatic updates'
    cmd_list_unsub = cmd_list + cmd_unsub
    cmd_list_sub = cmd_list + cmd_sub

    remote_error = 'Sorry, I\'m having some difficulty accessing the LLJ website. ' + \
                   'Please try again later.'

    feedback_string = 'Please reply with your feedback. ' + \
                      'I will relay the message to my developer.'
    feedback_alert = 'Feedback from {} ({}){}:\n{}'
    feedback_success = 'Your message has been sent to my developer. Thanks for your feedback, {}!'

    def post(self):
        data = json.loads(self.request.body)
        logging.info(self.request.body)

        msg = data.get('message')
        msg_chat = msg.get('chat')
        msg_from = msg.get('from')

        if msg_chat.get('type') == 'private':
            id = msg_from.get('id')
            first_name = msg_from.get('first_name')
            last_name = msg_from.get('last_name')
            username = msg_from.get('username')
        else:
            id = msg_chat.get('id')
            first_name = msg_chat.get('title')
            last_name = None
            username = None

        user = updateProfile(id, username, first_name, last_name)

        actual_id = msg_from.get('id')
        name = first_name.encode('utf-8', 'ignore').strip()
        actual_username = msg_from.get('username')
        if actual_username:
            actual_username = actual_username.encode('utf-8', 'ignore').strip()
        actual_name = msg_from.get('first_name').encode('utf-8', 'ignore').strip()
        actual_last_name = msg_from.get('last_name')
        if actual_last_name:
            actual_last_name = actual_last_name.encode('utf-8', 'ignore').strip()
        text = msg.get('text')
        if text:
            text = text.encode('utf-8', 'ignore')

        msg_reply = msg.get('reply_to_message')
        if msg_reply and str(msg_reply.get('from').get('id')) == bot_id and \
                         msg_reply.get('text') == self.feedback_string:
            name_string = actual_name
            if actual_last_name:
                name_string += ' ' + actual_last_name
            if actual_username:
                name_string += ' @' + actual_username

            if user.isGroup():
                group_string = ' via group {} ({})'.format(name, id)
            else:
                group_string = ''

            msg_dev = self.feedback_alert.format(name_string, actual_id, group_string, text)
            msg_user = self.feedback_success.format(actual_name)

            sendMessage(admin_id, msg_dev)
            sendMessage(id, msg_user)
            return

        if user.last_sent == None or text == '/start':
            if user.last_sent == None:
                new_user = True
            else:
                new_user = False

            if not user.isActive():
                user.setActive(True)

            if user.isGroup():
                response = 'Hello, friends in ' + name + \
                           '! Thanks for adding me in! This group chat is now subscribed.'
            else:
                response = 'Hello, ' + name + '! Welcome! You are now subscribed.'
            response += ' You may enter one of the following commands:' + self.cmd_list_unsub
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

        cmd = text.lower().strip()
        short_cmd = ''.join(cmd.split())

        def isCommand(word):
            flexi_pattern = ('/{}@lljbot'.format(word), '@lljbot/{}'.format(word))
            return cmd == '/' + word or short_cmd.startswith(flexi_pattern)

        if isCommand('subscribe'):
            if user.isActive():
                response = 'Looks like you are already subscribed!'
            else:
                user.setActive(True)
                response = 'Success!'
            response += ' You will receive material every day at midnight, Singapore time :)'

            sendMessage(id, response)
            return

        elif isCommand('unsubscribe'):
            if not user.isActive():
                response = 'Looks like you already unsubscribed! ' + \
                           'Don\'t worry; you won\'t be receiving any more automatic updates.'
            else:
                user.setActive(False)
                response = 'You have successfully unsubscribed and will no longer ' + \
                           'receive automatic updates. Use /subscribe if this was a mistake.'
            response += ' You can still get material manually by using the commands :)'

            sendMessage(id, response)
            return

        elif isCommand('today'):
            response = getDevo()
            if response == None:
                response = self.remote_error

            sendMessage(id, response, markdown=True)
            return

        elif isCommand('yesterday'):
            response = getDevo(-1)
            if response == None:
                response = self.remote_error

            sendMessage(id, response, markdown=True)
            return

        elif isCommand('tomorrow'):
            response = getDevo(1)
            if response == None:
                response = self.remote_error

            sendMessage(id, response, markdown=True)
            return

        elif isCommand('feedback'):
            response = self.feedback_string

            sendMessage(id, response, force=True)
            return

        else:
            if user.isGroup() and '@lljbot' not in cmd:
                return

            response = 'Sorry ' + actual_name + ', I couldn\'t understand that. ' + \
                       'Please enter one of the following commands:'
            if user.isActive():
                response += self.cmd_list_unsub
            else:
                response += self.cmd_list_sub

            sendMessage(id, response)
            return

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
        logging.info(self.request.body)

        params = json.loads(self.request.body)
        auto = params.get('auto')
        data = params.get('data')
        uid = json.loads(data).get('chat_id')

        try:
            result = telegramPost(data)
        except urlfetch_errors.Error as e:
            logging.warning('Error sending message to uid ' + str(uid) + ':\n' + str(e))
            self.abort(502)

        response = json.loads(result.content)
        existing_user = getUser(uid)

        if response.get('ok') == True:
            msg_id = response.get('result').get('message_id')
            logging.info('Message ' + str(msg_id) + ' sent to uid ' + str(uid))
            if existing_user:
                existing_user.updateLastSent()
                if auto:
                    existing_user.updateLastAuto()
        else:
            if response.get('description') == '[Error]: Bot was kicked from a chat':
                logging.info('Bot was kicked from uid ' + str(uid))
                if existing_user:
                    existing_user.setActive(False)
            else:
                logging.warning('Error sending message to uid ' + str(uid) + ':\n' + result.content)
                self.abort(502)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + token, LljPage),
    ('/send', SendPage),
    ('/retry', RetryPage),
    ('/message', MessagePage),
], debug=True)