import webapp2
from lljbot import User
from datetime import timedelta

class AdminPage(webapp2.RequestHandler):
    def get(self):
        def prep_str(str):
            return str.encode('utf-8', 'ignore')

        def prep_date(date):
            date = date + timedelta(hours=8)
            return date.strftime("%d %b %H:%M:%S")

        def prep_active(active):
            if active:
                return prep_str(u'\U00002714')
            else:
                return ''

        def prep_group(uid):
            if int(uid) < 0:
                return prep_str(u'\U00002714')
            else:
                return ''

        query = User.all()
        query.order('-created')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8'
        self.response.write('<html>\n<head>\n<title>LLJ Bot Admin</title>\n</head>\n<body>\n' +
                            '<table border="1" style="border: 1px solid black; border-collapse: collapse; padding: 10px;">\n')
        self.response.write('<tr><th>#</th><th>Chat ID</th><th>Name</th>' +
                            '<th>Created</th><th>Last received</th><th>Last sent</th><th>Active</th><th>Group</th></tr>\n')
        result = query.run()
        i = query.count()
        for user in result:
            uid = prep_str(user.key().name())
            name = prep_str(user.first_name)
            if user.last_name:
                name += ' ' + prep_str(user.last_name)
            if user.username:
                name += ' @' + prep_str(user.username)
            ctime = prep_date(user.created)
            rtime = prep_date(user.last_received)
            stime = prep_date(user.last_sent)
            active = prep_active(user.active)
            group = prep_group(uid)
            self.response.write(('<tr><td>{}</td><td>{}</td><td>{}</td>' +
                                '<td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n')
                                .format(i, uid, name, ctime, rtime, stime, active, group))
            i -= 1
        self.response.write('</table>\n</body>\n</html>')

app = webapp2.WSGIApplication([
    ('/admin', AdminPage),
], debug=True)