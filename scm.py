#!/usr/bin/env python

from invoke import task, run
import formic
import hgapi
from blessings import Terminal
import os

t = Terminal()

def get_repos(pattern):
    pattern = "**/%s/.hg/hgrc"%pattern
    return formic.FileSet(include=pattern, default_excludes=False)

@task
def status_hg(show=False, pattern='**'):
    fileset = get_repos(pattern)
    for file_name in fileset.qualified_files():
        path_repo = "/".join(file_name.split('/')[:-2])
        repo_name = file_name.split('/')[-3:-2][0]
        repo = hgapi.Repo(path_repo)
        st = repo.hg_status(empty=True)

        if not st:
            if show:
                print repo_name, t.bold_green('Ok')
            continue
        else:
            if show:
                print t.bold_red(repo_name),  t.bold_red('Ko')
            else:
                print t.bold_red(repo_name),  t.bold_red('Ko')
            if st.get('A'):
                print t.bold('Files Added')
                for file_name in st['A']:
                    print '  ' + t.green(file_name)
            if st.get('M'):
                print t.bold('Files Modified')
                for file_name in st['M']:
                    print '  ', t.yellow(file_name)
            if st.get('R'):
                print t.bold('Files Removed')
                for file_name in st['R']:
                    print '  ' + t.red(file_name)
            if st.get('!'):
                print t.bold('Files Deleted')
                for file_name in st['!']:
                    print '  ' + t.bold_red(file_name)
            if st.get('?'):
                print t.bold('Files Not Tracked')
                for file_name in st['?']:
                    print '  ' + t.blue(file_name)


@task
def status(show=False):
    status_hg(show)


@task
def hg_diff(pattern='**'):
    fileset = get_repos(pattern)
    for file_name in fileset.qualified_files():
        path_repo = "/".join(file_name.split('/')[:-2])
        repo_name = file_name.split('/')[-3:-2][0]
        repo = hgapi.Repo(path_repo)
        print t.bold(repo_name+" ======================")
        for diff in repo.hg_diff():
            print diff['diff']

@task
def diff(pattern='**'):
    hg_diff(pattern)


@task
def ppush(pattern='**'):
    fileset = get_repos(pattern)
    for file_name in fileset.qualified_files():
        path_repo = "/".join(file_name.split('/')[:-2])
        repo_name = file_name.split('/')[-3:-2][0]
        repo_name = file_name.split('/')[-3:-2][0]
        repo = hgapi.Repo(path_repo)
        print t.bold(repo_name+" ======================")
        cmd = ['outgoing']
        print repo.hg_command(*cmd)
        #run('cd %s; hg outgoing --stat'%path_repo)

@task
def summary(pattern='**'):
    fileset = get_repos(pattern)
    for file_name in fileset.qualified_files():
        path_repo = "/".join(file_name.split('/')[:-2])
        repo_name = file_name.split('/')[-3:-2][0]
        repo_name = file_name.split('/')[-3:-2][0]
        repo = hgapi.Repo(path_repo)
        print t.bold(repo_name+" ======================")
        cmd = ['summary','--remote']
        print repo.hg_command(*cmd)
        #run('cd %s; hg outgoing --stat'%path_repo)


