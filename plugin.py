###
# Copyright (c) 2006-2011, Gavin Gilmour
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
from supybot.utils.structures import TimeoutQueue
import re
import urllib
import urllib2
import sgmllib
import popen2
import random
import sys
import os
import time
from SOAPpy import WSDL
from optparse import OptionParser
from xml.dom import minidom
from urllib2 import Request, urlopen
from BeautifulSoup import BeautifulSoup

GROUPHUG_URL = 'http://grouphug.us/'
HUG_PATTERN = r'<div class="content">(.*?)<\/div>'
LYRICWIKI_WDSL = "http://lyricwiki.org/server.php?wsdl"
FILE_PATTERN = r"""File\s*:\s*<a href="(.*src/\d.+\.jpg)" target="_blank">\d.+\.jpg.+?</a>"""
BOARD_TYPES = {
    "an" : "zip", "a" : "zip", "b" : "img", "cgl" : "orz", "ck" : "cgi",
    "cm" : "zip", "co" : "cgi", "c" : "zip", "d" : "orz", "e" : "orz",
    "gif" : "cgi", "g" : "zip", "h" : "orz", "hr" : "orz", "k" : "zip",
    "mu" : "cgi", "m" : "zip", "n" : "orz", "o" : "zip", "po" : "cgi",
    "p" : "zip", "r" : "cgi", "s" : "cgi", "t" : "cgi", "tv" : "cgi",
    "u" : "orz", "v" : "zip", "wg" : "orz", "w" : "zip", "y" : "orz",
    "hc" : "cgi"
}

class Farm(callbacks.Plugin):
    """Main turnipfarm function class"""

    class Stripper(sgmllib.SGMLParser):
        """Handy sgml stripper class"""

        def __init__(self):
            sgmllib.SGMLParser.__init__(self)

        def strip(self, some_html):
            self.theString = ""
            self.feed(some_html)
            self.close()
            return self.theString

        def handle_data(self, data):
            self.theString += data

    def __init__(self, irc):
        self.__parent = super(Farm, self)
        self.__parent.__init__(irc)
        self.hugPattern = re.compile(HUG_PATTERN, re.DOTALL)
        self.linkPattern = re.compile(FILE_PATTERN)
        self.splitters = TimeoutQueue(60)

    def _color(self, c, fg=None):
        if c == ' ':
            return c
        if fg is None:
            fg = str(random.randint(2, 15)).zfill(2)
        return '\x03%s%s' % (fg, c)

    def _reply(self, irc, msg, mate=True):
        if mate:
            msg = msg + ' m8'
        irc.reply(msg.lower())


    def figlet(self, irc, msg, args, text):
        """<text>

        FIGLETs <text>
        """
        figletCmd = self.registryValue('figlet.command')
        if figletCmd:
            inst = popen2.Popen4([figletCmd, text])
            (r, w) = (inst.fromchild, inst.tochild)
            try:
                lines = r.readlines()
                if lines:
                    # config help protocols.irc.throttletime 1.0 ;-)
                    for line in lines:
                        irc.reply(line.strip('\r\n'))
                else:
                    self._reply(irc, "no figlet installed")
            finally:
                r.close()
                w.close()
                inst.wait()
        else:
            irc.error('couldn\'t find the figlet on this system.  '
                      'reconfigure supybot.plugins.Farm.figlet.command')

    figlet = wrap(figlet, ['text'])


    def hug(self, irc, msg, args, query):
        """[<query>]

        Returns a random hug from grouphug.us. <query> is only necessary if a
        hug containing this particular query is needed.
        """

        if query is not None:
            hugURL = GROUPHUG_URL + 'search?q=' + urllib.quote(query)
        else:
            hugURL = GROUPHUG_URL + 'random'

        hugHandle = None
        hugList = []
        stripper = self.Stripper()

        try:
            try:
                hugHandle = urllib2.urlopen(hugURL)
                hugList = self.hugPattern.findall(hugHandle.read())

                if len(hugList) > 0:
                    randomHug = hugList[random.randrange(len(hugList))]
                    randomHug = randomHug.replace('&nbsp;', ' ');
                    hug = stripper.strip(randomHug).strip()

                    # Colourize any particular terms
                    if query and self.registryValue('hug.highlightQuery'):
                        hug = hug.replace(query, self._color(query, fg=4) + '\x03')

                    irc.reply(hug.strip('\''))
                else:
                    self._reply(irc, "nothing found")
            except Exception, e:
                self._reply(irc, "timeout")
        finally:
            if hugHandle:
                hugHandle.close()

    hug = wrap(hug, [optional("something")])

    def lyrics(self, irc, msg, args, artist, title):
        """<artist> <title>

        Tries to find lyrics for <title> by <artist> from lyricwiki.org
        """

        proxy = WSDL.Proxy(LYRICWIKI_WDSL)

        try:
            if proxy.checkSongExists(artist, title):
                info = proxy.getSong(artist, title)
                lyrics = info['lyrics']
                irc.reply(lyrics)
            else:
                self._reply(irc, "nothing found")
        except:
            self._reply(irc, "timeout")

    lyrics = wrap(lyrics, ['something', 'something'])


    def fourchan(self, irc, msg, args, board):
        """<board>

        Returns a random image from a given 4chan.org board. If no board is
        given, a random board is picked (danger).
        """

        if board is None:
            board, value = random.choice(BOARD_TYPES.items())

        if not BOARD_TYPES.has_key(board):
                self._reply(irc, "no board")
                return

        type = BOARD_TYPES[board]

        handle = None
        imageList = []

        try:
            try:
                handle = urllib2.urlopen(os.path.join('http://%s.4chan.org' % type, board, 'imgboard.html'))
                imageList = self.linkPattern.findall(handle.read())
                boardImage = imageList[random.randrange(len(imageList))]
                irc.reply(boardImage)
            except Exception, e:
                self._reply(irc, "timeout")
        finally:
            if handle:
                handle.close()

    fourchan = wrap(fourchan, [optional('something')])

    def image(self, irc, msg, args, keyword):
        """<keyword>
        Replies with an image from Google Images.
        """
        try:
            url = """http://images.google.com/search?q=%s&hl=en&gbv=1&tbm=isch&ei=xs85TsmUN47OsgaE09nyDw&sa=N&safe=off"""
            url = url % (keyword.replace(' ', '+'))
            data = utils.web.getUrl(url, None, headers={'User-Agent' : "Mozilla/1.22 (compatible; MSIE 2.0; Windows 3.1)"})
            links = BeautifulSoup(data).findAll('a', href=True)

            matches = []
            for link in links:
                regex = re.findall('imgurl=(.+)(\.jpg+|\.png+|\.gif)', str(link))
                if regex != []:
                    matches.append(regex[0][0]+regex[0][1])

            irc.reply(random.choice(matches))
        except:
            self._reply(irc, "error")

    image = wrap(image, ['text'])

Class = Farm

# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
