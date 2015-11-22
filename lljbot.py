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
        logging.warning('Error fetching devo:\n' + str(e))
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

from secrets import TOKEN, ADMIN_ID, BOT_ID
TELEGRAM_URL = 'https://api.telegram.org/bot' + TOKEN
TELEGRAM_URL_SEND = TELEGRAM_URL + '/sendMessage'
JSON_HEADER = {'Content-Type': 'application/json;charset=utf-8'}

def telegramPost(data, deadline=3):
    return urlfetch.fetch(url=TELEGRAM_URL_SEND, payload=data, method=urlfetch.POST,
                          headers=JSON_HEADER, deadline=deadline)

class User(db.Model):
    username = db.StringProperty(indexed=False)
    first_name = db.StringProperty(multiline=True, indexed=False)
    last_name = db.StringProperty(multiline=True, indexed=False)
    created = db.DateTimeProperty(auto_now_add=True)
    last_received = db.DateTimeProperty(auto_now_add=True, indexed=False)
    last_sent = db.DateTimeProperty(indexed=False)
    last_auto = db.DateTimeProperty(default=datetime.fromtimestamp(0))
    active = db.BooleanProperty(default=True)
    promo = db.BooleanProperty(default=False)

    def getUid(self):
        return self.key().name()

    def isGroup(self):
        return int(self.getUid()) < 0

    def isActive(self):
        return self.active

    def isPromo(self):
        return self.promo

    def setActive(self, active):
        self.active = active
        self.put()

    def setPromo(self, promo):
        self.promo = promo
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

def sendMessage(user_or_uid, text, auto=False, force=False, markdown=False, promo=False):
    try:
        uid = str(user_or_uid.getUid())
        user = user_or_uid
    except AttributeError:
        uid = str(user_or_uid)
        user = getUser(user_or_uid)

    def sendShortMessage(text):
        build = {
            'chat_id': uid,
            'text': text
        }

        if force:
            build['reply_markup'] = {'force_reply': True}
        if markdown:
            build['parse_mode'] = 'Markdown'
        if promo:
            build['disable_web_page_preview'] = True

        data = json.dumps(build)

        def queueMessage():
            payload = json.dumps({
                'auto': auto,
                'promo': promo,
                'data': data
            })
            taskqueue.add(url='/message', payload=payload)

        try:
            if auto or promo:
                #result = telegramPost(data, 1)
                queueMessage()
                return
            else:
                result = telegramPost(data)
        except urlfetch_errors.Error as e:
            logging.warning('Error sending message to uid ' + uid + ':\n' + str(e))
            queueMessage()
            return

        response = json.loads(result.content)

        if response.get('ok') == True:
            msg_id = str(response.get('result').get('message_id'))
            logging.info('Message ' + msg_id  + ' sent to uid ' + uid)
            if user:
                user.updateLastSent()
                if auto:
                    user.updateLastAuto()
                if promo:
                    user.setPromo(True)
        else:
            error_description = response.get('description')
            if error_description == '[Error]: Bot was kicked from a chat' or \
               error_description == '[Error]: Bad Request: group is deactivated' or \
               error_description == '[Error]: PEER_ID_INVALID' or \
               error_description == '[Error]: Forbidden: bot was kicked from the group chat':
                logging.info('Bot was kicked from uid ' + uid)
                if user:
                    user.setActive(False)
            else:
                logging.warning('Error sending message to uid ' + uid + ':\n' + result.content)
                if error_description.startswith('[Error]: Bad Request: can\'t parse message'):
                    if build.get('parse_mode'):
                        del build['parse_mode']
                    data = json.dumps(build)
                queueMessage()

    if len(text) > 4096:
        chunks = textwrap.wrap(text, width=4096, replace_whitespace=False, drop_whitespace=False)
        for chunk in chunks:
            sendShortMessage(chunk)
    else:
        sendShortMessage(text)

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('LLJBot backend running...\n')

class LljPage(webapp2.RequestHandler):
    CMD_LIST = '\n\n' + \
                   '/today - get today\'s material\n' + \
                   '/yesterday - get yesterday\'s material\n' + \
                   '/tomorrow - get tomorrow\'s material'
    CMD_UNSUB = '\n/unsubscribe - disable automatic updates'
    CMD_SUB = '\n/subscribe - re-enable automatic updates'
    CMD_LIST_UNSUB = CMD_LIST + CMD_UNSUB
    CMD_LIST_SUB = CMD_LIST + CMD_SUB
    RATE_LINK = '\n\nEnjoy using LLJ Bot? Click the link below to rate it!\n' + \
                'https://telegram.me/storebot?start=lljbot'

    REMOTE_ERROR = 'Sorry, I\'m having some difficulty accessing the LLJ website. ' + \
                   'Please try again later.'

    FEEDBACK_STRING = 'Please reply with your feedback. ' + \
                      'I will relay the message to my developer.'
    FEEDBACK_ALERT = 'Feedback from {} ({}){}:\n{}'
    FEEDBACK_SUCCESS = 'Your message has been sent to my developer. ' + \
                       'Thanks for your feedback, {}!'

    def post(self):
        data = json.loads(self.request.body)
        logging.info(self.request.body)

        msg = data.get('message')
        msg_chat = msg.get('chat')
        msg_from = msg.get('from')

        if msg_chat.get('type') == 'private':
            uid = msg_from.get('id')
            first_name = msg_from.get('first_name')
            last_name = msg_from.get('last_name')
            username = msg_from.get('username')
        else:
            uid = msg_chat.get('id')
            first_name = msg_chat.get('title')
            last_name = None
            username = None

        user = updateProfile(uid, username, first_name, last_name)

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

        def getNameString():
            name_string = actual_name
            if actual_last_name:
                name_string += ' ' + actual_last_name
            if actual_username:
                name_string += ' @' + actual_username
            return name_string

        msg_reply = msg.get('reply_to_message')
        if msg_reply and str(msg_reply.get('from').get('id')) == BOT_ID and \
                         msg_reply.get('text') == self.FEEDBACK_STRING:

            if user.isGroup():
                group_string = ' via group {} ({})'.format(name, uid)
            else:
                group_string = ''

            msg_dev = self.FEEDBACK_ALERT.format(getNameString(), actual_id, group_string, text)
            msg_user = self.FEEDBACK_SUCCESS.format(actual_name)

            sendMessage(ADMIN_ID, msg_dev)
            sendMessage(user, msg_user)
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
            response += ' You may enter one of the following commands:' + self.CMD_LIST_UNSUB
            response += '\n\nIn the meantime, here\'s today\'s material to get you started!'
            sendMessage(user, response)

            response = getDevo()
            if response == None:
                response = self.REMOTE_ERROR
            sendMessage(user, response, markdown=True)

            if new_user:
                if user.isGroup():
                    new_alert = 'New group: "{}" via user: {}'.format(name, getNameString())
                else:
                    new_alert = 'New user: ' + getNameString()
                sendMessage(ADMIN_ID, new_alert)

            return

        if text == None:
            logging.info('No text detected')
            return

        logging.info(text)

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

            sendMessage(user, response)
            return

        elif isCommand('unsubscribe') or isCommand('stop'):
            if not user.isActive():
                response = 'Looks like you already unsubscribed! ' + \
                           'Don\'t worry; you won\'t be receiving any more automatic updates.'
            else:
                user.setActive(False)
                response = 'You have successfully unsubscribed and will no longer ' + \
                           'receive automatic updates. Use /subscribe if this was a mistake.'
            response += ' You can still get material manually by using the commands :)'

            sendMessage(user, response)
            return

        elif isCommand('settings'):
            if user.isActive():
                response = 'You are currently *subscribed*. ' + \
                           'Use /unsubscribe to change this.'
            else:
                response = 'You are currently *not subscribed*. ' + \
                           'Use /subscribe if this is a mistake.'

            sendMessage(user, response, markdown=True)
            return

        elif isCommand('today'):
            response = getDevo()
            if response == None:
                response = self.REMOTE_ERROR

            sendMessage(user, response, markdown=True)
            return

        elif isCommand('yesterday'):
            response = getDevo(-1)
            if response == None:
                response = self.REMOTE_ERROR

            sendMessage(user, response, markdown=True)
            return

        elif isCommand('tomorrow'):
            response = getDevo(1)
            if response == None:
                response = self.REMOTE_ERROR

            sendMessage(user, response, markdown=True)
            return

        elif isCommand('feedback'):
            response = self.FEEDBACK_STRING

            sendMessage(user, response, force=True)
            return

        elif isCommand('help'):
            response = 'Hi ' + actual_name + ', please enter one of the following commands:'
            if user.isActive():
                response += self.CMD_LIST_UNSUB
            else:
                response += self.CMD_LIST_SUB
            response += self.RATE_LINK

            sendMessage(user, response)
            return

        else:
            logging.info('Unrecognised command')
            if user.isGroup() and '@lljbot' not in cmd:
                return

            response = 'Sorry ' + actual_name + ', I couldn\'t understand that. ' + \
                       'Please enter one of the following commands:'
            if user.isActive():
                response += self.CMD_LIST_UNSUB
            else:
                response += self.CMD_LIST_SUB

            sendMessage(user, response)
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
                for user in query.run(batch_size=500):
                    sendMessage(user, devo, auto=True, markdown=True)
            except db.Error as e:
                logging.warning('Error reading from datastore:\n' + str(e))
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
            try:
                for user in query.run(batch_size=500):
                    sendMessage(user, devo, auto=True, markdown=True)
            except db.Error as e:
                logging.warning('Error reading from datastore:\n' + str(e))
                self.abort(502)
        else:
            self.abort(502)

class PromoPage(webapp2.RequestHandler):
    def get(self):
        taskqueue.add(url='/promo')

    def post(self):
        three_days_ago = datetime.now() - timedelta(days=3)
        query = User.all()
        query.filter('promo =', False)
        query.filter('created <', three_days_ago)
        for user in query.run(batch_size=500):
            name = user.first_name.encode('utf-8', 'ignore').strip()
            if user.isGroup():
                promo_msg = 'Hello, friends in {}! Do you find LLJ Bot useful?'.format(name)
            else:
                promo_msg = 'Hi {}, do you find LLJ Bot useful?'.format(name)
            promo_msg += ' Why not rate it on the bot store (you don\'t have to exit' + \
                         ' Telegram)!\nhttps://telegram.me/storebot?start=lljbot'
            sendMessage(user, promo_msg, promo=True)

class MigratePage(webapp2.RequestHandler):
    def get(self):
        # query = User.all()
        # for user in query.run(batch_size=1000):
        #     user.setPromo(False)
        return

class MessagePage(webapp2.RequestHandler):
    def post(self):
        params = json.loads(self.request.body)
        auto = params.get('auto')
        promo = params.get('promo')
        data = params.get('data')
        uid = str(json.loads(data).get('chat_id'))

        try:
            result = telegramPost(data, 4)
        except urlfetch_errors.Error as e:
            logging.warning('Error sending message to uid ' + uid + ':\n' + str(e))
            logging.warning(data)
            self.abort(502)

        response = json.loads(result.content)
        user = getUser(uid)

        if response.get('ok') == True:
            msg_id = str(response.get('result').get('message_id'))
            logging.info('Message ' + msg_id + ' sent to uid ' + uid)
            if user:
                user.updateLastSent()
                if auto:
                    user.updateLastAuto()
                if promo:
                    user.setPromo(True)
        else:
            error_description = response.get('description')
            if error_description == '[Error]: Bot was kicked from a chat' or \
               error_description == '[Error]: Bad Request: group is deactivated' or \
               error_description == '[Error]: PEER_ID_INVALID' or \
               error_description == '[Error]: Forbidden: bot was kicked from the group chat':
                logging.info('Bot was kicked from uid ' + uid)
                if user:
                    user.setActive(False)
            else:
                logging.warning('Error sending message to uid ' + uid + ':\n' + result.content)
                logging.warning(data)
                self.abort(502)

app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/' + TOKEN, LljPage),
    ('/send', SendPage),
    ('/retry', RetryPage),
    ('/message', MessagePage),
    ('/promo', PromoPage),
    ('/migrate', MigratePage),
], debug=True)
