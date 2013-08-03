#!/usr/bin/env python

from invoke import task, run
import hgapi
from blessings import Terminal
import os
import ConfigParser
from multiprocessing import Process

t = Terminal()
Config = ConfigParser.ConfigParser()

for r,d,f in os.walk("./config"):
    for files in f:
        if files.endswith(".cfg"):
            Config.readfp(open(os.path.join(r,files)))

@task
def clone():

    def hg_clone(module, url, path):
        print "Adding Module " + t.bold(module) + " to clone list"
        repo_path = os.path.join(path, module)
        if os.path.exists(repo_path):
            print "Path " + t.bold(repo_path) + t.red(" Already exists")
        else:
            run('hg clone -q %s %s' % (url, repo_path))
            print "Repo " + t.bold(repo_path) + t.green(" Cloned")

    for section in Config.sections():
        repo = Config.get(section, 'repo')
        url = Config.get(section, 'url')
        path = Config.get(section, 'path')
        func = hg_clone
        if repo != 'hg':
            print "Not developet yet"
            continue
        p = Process(target=func, args=(section, url, path))
        p.start()

    p.join()


@task
def status(verbose=False):

    def hg_status(module, path, verbose):
        repo_path = os.path.join(path, module)
        if not os.path.exists(repo_path):
            print t.red("Missing repositori:") + t.bold(repo_path)
            return
        repo = hgapi.Repo(repo_path)
        st = repo.hg_status(empty=True)
        if not st and verbose:
            print module, t.bold_green('OK')
            return
        if not st and not verbose:
            return

        msg = [t.bold_red("\n"+ module + ':Not OK')]

        if st.get('A'):
            msg.append(t.bold('Files Added'))
            for file_name in st['A']:
                msg.append('  ' + t.green(file_name))
        if st.get('M'):
            msg.append(t.bold('Files Modified'))
            for file_name in st['M']:
                msg.append('  ' + t.yellow(file_name))
        if st.get('R'):
            msg.append(t.bold('Files Removed'))
            for file_name in st['R']:
                msg.append('  ' + t.red(file_name))
        if st.get('!'):
            msg.append(t.bold('Files Deleted'))
            for file_name in st['!']:
                msg.append('  ' + t.bold_red(file_name))
        if st.get('?'):
            msg.append(t.bold('Files Not Tracked'))
            for file_name in st['?']:
                msg.append('  ' + t.blue(file_name))

        print "\n".join(msg)

    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_status
        if repo != 'hg':
            print "Not developet yet"
            continue
        p = Process(target=func, args=(section, path, verbose))
        p.start()
    p.join()


@task
def diff(verbose=False):
    def hg_diff(module, path, verbose):
        path_repo = os.path.join(path, module)
        if not os.path.exists(path_repo):
            print t.red("Missing repositori:") + t.bold(path_repo)
            return
        if not verbose:
            print t.bold(module+"\n")
            run('cd %s; hg diff --stat' % path_repo)
            return

        repo = hgapi.Repo(path_repo)
        for diff in repo.hg_diff():
            if diff:
                print t.bold(module+"\n")
                print diff['diff']

    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        hg_diff(section, path, verbose)


@task
def summary(verbose=False):
    def hg_summary(module, path, verbose):
        path_repo = os.path.join(path, module)
        if not os.path.exists(path_repo):
            print t.red("Missing repositori:") + t.bold(path_repo)
            return
        repo = hgapi.Repo(path_repo)
        cmd = ['summary','--remote']
        summary = repo.hg_command(*cmd)
        print t.bold("= " + module +" =")
        print summary

    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_summary
        if repo != 'hg':
            print "Not developet yet"
            continue
        p = Process(target=func, args=(section, path, verbose))
        p.start()
    p.join()


@task
def ppush(verbose=False):
    def hg_ppush(module, path, verbose):
        path_repo = os.path.join(path, module)
        if not os.path.exists(path_repo):
            print t.red("Missing repositori:") + t.bold(path_repo)
            return
        repo = hgapi.Repo(path_repo)
        cmd = ['outgoing']
        if verbose:
            cmd.append('-v')
        try:
            out = repo.hg_command(*cmd)
        except:
            #TODO:catch correct exception
            return
        print t.bold("= " + module +" =")
        print out

    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_ppush
        if repo != 'hg':
            print "Not developet yet"
            continue
        p = Process(target=func, args=(section, path, verbose))
        p.start()
    p.join()

