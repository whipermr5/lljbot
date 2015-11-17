import webapp2
from lljbot import User
from datetime import timedelta

class AdminPage(webapp2.RequestHandler):
    def get(self):
        def prep_str(str):
            if str == None:
                return '-'
            return str.encode('utf-8', 'ignore')

        def prep_date(date):
            date = date + timedelta(hours=8)
            return date.strftime("%d/%m/%y %H:%M:%S")

        query = User.all()
        query.order('-created')
        self.response.headers['Content-Type'] = 'text/html; charset=utf-8'
        self.response.write('<html>\n<head>\n<title>LLJ Bot Admin</title>\n</head>\n<body>\n<table>\n')
        self.response.write('<tr><td>#</td><td>Chat ID</td><td>First name</td><td>Last name</td><td>Username</td>' +
                            '<td>Created</td><td>Last received</td><td>Last sent</td><td>Active</td></tr>\n')
        result = query.run()
        i = query.count()
        for user in result:
            uid = prep_str(user.key().name())
            fname = prep_str(user.first_name)
            lname = prep_str(user.last_name)
            uname = prep_str(user.username)
            ctime = prep_date(user.created)
            rtime = prep_date(user.last_received)
            stime = prep_date(user.last_sent)
            active = user.active
            self.response.write(('<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td>' +
                                '<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>\n')
                                .format(i, uid, fname, lname, uname, ctime, rtime, stime, active))
            i -= 1
        self.response.write('</table>\n</body>\n</html>')

app = webapp2.WSGIApplication([
    ('/admin', AdminPage),
], debug=True)