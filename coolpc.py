# -*- coding: utf-8 -*-
import subprocess as sp
import sys
import datetime as dt
import sqlite3

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

def main():
  db_conn = sqlite3.connect('coolpc.db')
  db_conn.text_factory = str
  db_csr = db_conn.cursor()
  now_str = dt.datetime.now().isoformat()
  dom = None
  if len(sys.argv) > 1:
    with open(sys.argv[1]) as f:
      dom = f.read()
  else:
    dom = sp.check_output(['chrome', '--headless', '--disable-gpu', '--dump-dom',
                           '--enable-logging',
                           'https://www.coolpc.com.tw/evaluate.php'])
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
      if 'disabled' in opt:
        continue
      data.append((label,) + getToks(opt) + (now_str,))
      # print ','.join(data[-1])

  if len(data) > 0:
    db_csr.executemany('insert into VideoCard values (?,?,?,?,?,?)', data)
    db_conn.commit()

if __name__ == '__main__':
  main()
