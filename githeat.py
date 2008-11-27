#!/usr/bin/env python
# githeat
# a git blame viewer
# usage: githeat.py <file>
# shows the file with annotations
# on author and age etc. per line.
import sys, subprocess
import re

import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango
import gtksourceview2
import time

class BlamedFile(object):
    class Commit(object):
        def __init__(self, sha1):
            self.sha1 = sha1
        def __repr__(self):
            return "<%s %s>"%(self.__class__.__name__,
                              ", ".join("%s = %s" % (key, value) for key, value in self.__dict__.iteritems()))

    class Line(object):
        def __init__(self, fileline, commit, sourceline, resultline, num_lines):
            self.text = fileline
            self.commit = commit
            self.sourceline = sourceline
            self.resultline = resultline
            self.num_lines = num_lines
        def __repr__(self):
            return "<Line (%s/%d/%s) %s>" % (self.sourceline, self.resultline, self.num_lines, self.commit)

    def __init__(self, fil):
        self.sha1_to_commit = {}
        self.commits = []
        self.lines = []
        self.text = ''
        filelines = open(fil).readlines()
        self.text = "".join(filelines)
        p = subprocess.Popen(["git-blame", "--incremental", fil],
                             shell=False,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        beginline = re.compile(r'(\w{40})\s+(\d+)\s+(\d+)\s+(\d+)')
        currcommit = None
        for line in p.stdout:
            bgm = beginline.match(line)
            if bgm:
                sha1 = bgm.group(1)
                if self.sha1_to_commit.has_key(sha1):
                    currcommit = self.sha1_to_commit[sha1]
                else:
                    currcommit = BlamedFile.Commit(sha1)
                    self.commits.append(currcommit)
                    self.sha1_to_commit[sha1] = currcommit
                sourceline = int(bgm.group(2))
                resultline = int(bgm.group(3))
                num_lines = int(bgm.group(4))
                blameline = BlamedFile.Line(filelines[resultline-1], currcommit, sourceline, resultline, num_lines)
                for _ in range(num_lines):
                    self.lines.append(blameline)
            elif currcommit:
                # parse metadata about blameline
                cmd, _, data = line.partition(' ')
                data = data.strip()
                cmd = cmd.replace('-', '_')

                if cmd == 'author_time' or cmd == 'committer_time':
                    data = int(data)

                if hasattr(currcommit, cmd):
                    assert getattr(currcommit, cmd) == data
                setattr(currcommit, cmd, data)

        self.lines.sort(lambda x,y: cmp(x.resultline, y.resultline))

        # calculate age (0 - 100 where 100 is oldest and 0 is newest)
        oldest = None
        newest = None
        for commit in self.commits:
            if hasattr(commit, 'author_time'):
                if not oldest or oldest > commit.author_time:
                    oldest = commit.author_time
                if not newest or newest < commit.author_time:
                    newest = commit.author_time
        if oldest != newest:
            for commit in self.commits:
                if hasattr(commit, 'author_time'):
                    commit.age = 100 - int(100 * (commit.author_time - oldest)) / (newest - oldest)
                else:
                    commit.age = 100
        else:
            for commit in self.commits:
                commit.age = 100
        #outerr = p.stderr.readlines()

def main(fil):
    blamed = BlamedFile(fil)
    if not blamed.lines:
        print "no lines to blame, sure this file is in a git repository?"
        sys.exit(1)

    win = gtk.Window()
    win.connect("destroy", lambda w: gtk.main_quit())
    win.connect("delete_event", lambda w, e: gtk.main_quit())

    bufferS = gtksourceview2.Buffer()
    manager = gtksourceview2.LanguageManager()
    stylemanager = gtksourceview2.StyleSchemeManager()
    if 'tango' in stylemanager.get_scheme_ids():
        bufferS.set_style_scheme(stylemanager.get_scheme('tango'))
    language = manager.guess_language(fil)
    #langS.set_mime_types(["text/x-python"])
    bufferS.set_language(language)
    #bufferS.set_highlight(True)
    view = gtksourceview2.View(bufferS)
    view.set_show_line_numbers(True)
    view.modify_font(pango.FontDescription('Monospace'))

    box = gtk.VBox()
    scroll = gtk.ScrolledWindow()
    scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    scroll.add(view)
    box.pack_start(scroll, expand=True, fill=True, padding=0)
    liststore = gtk.ListStore(str, str)
    treeview = gtk.TreeView(liststore)
    col = gtk.TreeViewColumn("Key", gtk.CellRendererText(), text=0)
    treeview.append_column(col)
    col = gtk.TreeViewColumn("Value", gtk.CellRendererText(), text=1)
    treeview.append_column(col)
    scroll = gtk.ScrolledWindow()
    scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
    scroll.add(treeview)
    scroll.set_property('height-request', 120)
    box.pack_end(scroll, expand=False, fill=True, padding=4)
    win.add(box)

    bufferS.set_text(blamed.text)

    def color_for_age(age):
        age = min(max(age, 0), 100)
        r = 255 - (age/3)
        g = 255 - (age/3)
        b = 255 - (age/3)
        return '#%02x%02x%02x'%(r,g,b)

    for age in range(101):
        # create marker type for age
        view.set_mark_category_background('age%d'%(age), gtk.gdk.color_parse(color_for_age(age)))
    
    for y in range(len(blamed.lines)):
        age = blamed.lines[y].commit.age
        line_start = bufferS.get_iter_at_line(y)
        bufferS.create_source_mark(None, 'age%d'%(age), line_start)
    

#    def on_move_cursor(textview, step_size, count, extend_selection):
#        buffer = textview.get_buffer()

    def on_mark_set(buffer, param, param2):
        iter = buffer.get_iter_at_mark(buffer.get_insert())
        liststore.clear()
        if iter.get_line() < len(blamed.lines):
            commit = blamed.lines[iter.get_line()].commit
            if commit:
                liststore.append(['Author', commit.author])
                liststore.append(['Email', commit.author_mail])
                liststore.append(['Time', time.ctime(commit.author_time)])
                liststore.append(['Summary', commit.summary])
                liststore.append(['SHA1', commit.sha1])
            #for key, val in commit.__dict__.iteritems():
            #    if key == 'author_time' or key == 'committer_time':
            #        val = time.ctime(val)
            #    liststore.append([key, val])
        
    
#    view.connect_after('move-cursor', on_move_cursor)
    bufferS.connect_after('mark-set', on_mark_set)
    
    win.show_all()
    win.resize(600,500)
    gtk.main()

if __name__=="__main__":
    if len(sys.argv) < 2:
        print "usage: %s <file>" % (sys.argv[0])
        sys.exit(1)
    main(sys.argv[1])