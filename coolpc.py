# -*- coding: utf-8 -*-
import argparse
import base64
import cStringIO
import datetime as dt
import httplib2
import mimetypes
import oauth2client as oauth
import oauth2client.file
import oauth2client.tools
import oauth2client.client
import os
import shutil
import sqlite3
import subprocess as sp
import sys

from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from googleapiclient.discovery import build

def matchTag(s, tag):
  '''
  Optimistic tags matching. Match result includes tag closure.
  |s| is string to be matched. |tag| is tag name such as `optgroup`.
  '''
  tagBeg = '<' + tag
  tagEnd = '</{}>'.format(tag)
  pos = 0
  beg = 0
  while True:
    pos = s.find(tagBeg, beg)
    if pos == -1:
      break
    beg = pos
    pos = s.find(tagEnd, beg)
    assert(pos != -1)
    yield s[beg:pos]
    beg = pos + len(tagEnd)

def getAttr(s, attr):
  '''
  Find value of 'attr' in |s|. Assuem format is
    attr="value"
  '''
  pos = s.find(attr+'="')
  if pos == -1:
    return
  pos += len(attr) + 2
  return s[pos:s.find('"', pos)]

def getToks(s):
  '''
  |s| is string containing multiple option tags of following format:
    <option ...>Vendor Product Note Price</option>
  '''
  pos = s.find('>')
  pos += 1
  beg = pos
  pos = s.find(' ', beg)
  vendor = s[beg:pos]

  pos += 1
  beg = pos
  pos = s.rfind(')', beg)
  pos += 1
  product = s[beg:pos]

  beg = pos
  pos = s.find(', ', beg)
  note = s[beg:pos]

  # $price[\$sale_price] (use sale price if any)
  pos += 2
  beg = pos
  pos = s.rfind('$', beg)
  pos += 1
  beg = pos
  pos = s.find(' ', beg)
  price = str(int(s[beg:pos]))
  return (vendor, product, note, price)

def userDataDir():
  map = {
    'nt': os.environ.get('LOCALAPPDATA', None),
    'posix': os.environ.get('HOME', None)
  }
  return os.path.join(map[os.name], '.coolpc')


class DB(object):
  '''
  Simple warpper for sqlite3 that apply some extra configuation.
  '''
  filename = 'coolpc.db'
  def __init__(self):
    self.file_path = os.path.join(userDataDir(), DB.filename)
    self.conn = self.connect()

  def connect(self):
    conn = sqlite3.connect(self.file_path)
    conn.text_factory = str
    return conn

  def update(self, data):
    db_csr = self.conn.cursor()
    db_csr.executemany('insert into VideoCard values (?,?,?,?,?,?)', data)
    self.conn.commit()

  def computeDiff(self):
    db_csr = self.conn.cursor()
    db_csr.execute('select vendor, product, price, diff from PriceDiff');
    output = cStringIO.StringIO()
    for vendor, prod, price, diff in db_csr:
      print >>output, vendor, prod, price, diff
    db_csr.execute('select * from Soldout')
    for (prod,) in db_csr:
      print >>output, '[soldout]', prod
    db_csr.execute('select * from NewArrival')
    for (vendor, prod, price) in db_csr:
      print >>output, '[new]', vendor, prod, price
    return output

def install(reset=False):
  user_dir = userDataDir()
  if reset is True:
    shutil.rmtree(user_dir, True)
  try:
    os.makedirs(user_dir)
  except Exception as e:
    pass
  shutil.copy(DB.filename, user_dir)

def fetchPage():
  '''
  Fetch web page with headless chrome. Assume chrome executble is in shell's
  search path.
  '''
  # TODO: Tweak args for platform other than win
  chromePath = 'chrome'
  if os.name == 'nt':
    chromePath = 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe';
  return sp.check_output([chromePath, '--headless', '--disable-gpu',
                          '--dump-dom',
                          '--enable-logging',
                          'https://www.coolpc.com.tw/evaluate.php'])

class MailAgent(object):
  api_scope = 'https://www.googleapis.com/auth/gmail.send'
  def __init__(self):
    sys.argv = []
    store = oauth.file.Storage('token.json')
    creds = store.get()
    if not creds or creds.invalid:
        flow = oauth.client.flow_from_clientsecrets('credentials.json',
                                                    MailAgent.api_scope)
        creds = oauth.tools.run_flow(flow, store)
    self.service = build('gmail', 'v1', http=creds.authorize(httplib2.Http()))

  def createMessage(self, sender, to, subject, message_text):
    message = MIMEText(message_text)
    message['to'] = to
    message['from'] = sender
    message['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(message.as_string())}

  def sendTest(self):
    msg = self.createMessage(
      'yangacer@gmail.com',
      'yangacer@gmail.com',
      'Coolpc test mail',
      'This is a test mail from coolpc crawler.')
    self.send(msg)

  def sendDiff(self, diff):
    msg = self.createMessage(
      'yangacer@gmail.com',
      'yangacer@gmail.com',
      '[Coolpc] Price Watchlist',
      diff)
    self.send(msg)


  def send(self, message):
    try:
      resp = (self.service.users().messages().send(userId='me', body=message)
                 .execute())
      print 'Message Id: %s' % resp['id']
    except errors.HttpError, error:
      print 'An error occurred: %s' % error

def parseArgs():
  parser = argparse.ArgumentParser()
  parser.add_argument('file', nargs='?', help='Read web page from file',
                      type=file)
  parser.add_argument('--install', '-i', help='Install user data (db).',
                      action='store_true')
  parser.add_argument('--dryrun', '-d', action='store_true')
  parser.add_argument('--verbose', '-v', action='store_true')
  parser.add_argument('--diff', action='store_true')
  parser.add_argument('--testmail', action='store_true')
  return parser.parse_args()

def main():
  args = parseArgs()

  if args.install is True:
    install()
    return

  db = DB()
  ma = MailAgent()

  if args.diff is True:
    output = db.computeDiff()
    diff = output.getvalue()
    if len(diff) > 0:
      print (diff,)
    else:
      print 'No price diff found'
    output.close()
    return

  if args.testmail is True:
    ma.sendTest()
    return

  now = dt.datetime.now()
  dom = args.file.read() if args.file is not None else fetchPage()
  data = []
  for grp in matchTag(dom, 'optgroup'):
    label = getAttr(grp, 'label').lower()
    if 'nvidia gt' in label or 'nvidia rt' in label:
      pass
    elif 'amd rx' in label or 'amd rx vega' in label:
      pass
    else:
      continue
    label = label.replace(' (無類比輸出)', '')
    for opt in matchTag(grp, 'option'):
      if 'disabled' in opt or '支援組裝' in opt or 'class="r"' in opt:
        continue
      data.append((label,) + getToks(opt) + (now.isoformat(),))
      if args.verbose is True:
        print ','.join(data[-1])

  if len(data) == 0:
    return

  if args.dryrun is False:
    db.update(data)
    output = db.computeDiff()
    diff = output.getvalue()
    if len(diff) > 0:
      ma.sendDiff(diff)
    else:
      print 'No price diff found'
    output.close()

if __name__ == '__main__':
  script_dir = os.path.dirname(os.path.abspath(__file__))
  os.chdir(script_dir)
  main()
