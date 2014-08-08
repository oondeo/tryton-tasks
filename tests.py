#!/usr/bin/env python
from invoke import task, run, Collection
import os
import tempfile
import scm
import utils
import project
from ConfigParser import NoOptionError

# from .scm import prefetch, fetch, get_repo, remove_dir,
#      hg_clone, git_clone
# from .utils import read_config_file


@task()
def test(output=None, coverage=False, flakes=False, fail_fast=True,
        dbtype='sqlite', mail=False, name=None, module=None, directory=None):

    test_file = 'test.py'
    if directory:
        test_file = os.path.join(directory, test_file)
    cmd = ['/usr/bin/env', 'python', test_file]
    if output:
        cmd += ['--output', output]

    if coverage:
        cmd.append('--coverage')
    if flakes:
        cmd.append('--flakes')
    if fail_fast:
        cmd.append('--fail-fast')
    cmd.append('--db-type %s' % dbtype)
    if mail:
        cmd.append('--mail')
    if name:
        cmd.append('--name %s' % name)
    if module:
        cmd.append('-m %s' % module)

    run(" ".join(cmd), echo=True)


@task
def runall(test_file, output, branch='default', exclude_stable=False,
        exclude_development=False, exclude_reviews=False):
    if not exclude_stable:
        print "Setup & testing stable revision of branch: %s " % branch
        setup(branch, development=False)
        runtests(test_file, output, branch, development=False,
            include_reviews=False)
        if not exclude_reviews:
            runtests(test_file, output, branch, development=False,
                include_reviews=True)
    if not exclude_development:
        print "Setup & testing development revision of branch: %s " % branch
        setup(branch, development=True)
        runtests(test_file, output, branch, development=True,
            include_reviews=False)
        if not exclude_reviews:
            runtests(test_file, output, branch, development=True,
                include_reviews=True)


@task
def runtests(test_file=None, output=None, branch='default', development=False,
        include_reviews=False):

    directory = tempfile.mkdtemp()
    run("cp . %s -R" % directory)
    sections = []
    if test_file:
        config = utils.read_config_file(test_file)
        sections = config.sections()

    coverage = True
    flakes = True
    fail_fast = False
    mail = True
    name_sufix = ''
    if development:
        name_sufix += ' - Development'

    if include_reviews:
        name_sufix += ' (with reviews)'
        project.fetch_reviews(branch, exclude_components=config.sections() +
            ['OpenERP'])
    name = 'Generic Modules'

    test(output, False, False, fail_fast, 'sqlite', mail, name,
        directory=directory)
    test(output, coverage, flakes, fail_fast, 'postgresql', mail, name,
        directory=directory)

    for section in sections:
        name = section + name_sufix
        if development:
            name = '%s - Development' % name
        repos_to_clone = [section]
        try:
            repos_to_clone += config.get(section, 'requires').split(',')
        except NoOptionError:
            pass

        repos_to_remove = []
        for to_clone in repos_to_clone:
            repo = scm.get_repo(to_clone, config, 'clone', development)
            if repo['branch'] != branch:
                continue
            func = repo['function']
            func(repo['url'], repo['path'], repo['branch'], repo['revision'])
            repos_to_remove.append(repo['path'])
        if include_reviews:
            name = '%s (with reviews)' % name
            project.fetch_reviews(component=section)
        test(output, False, False, fail_fast, 'sqlite', mail, name, section,
            directory=directory)
        test(output, coverage, flakes, fail_fast, 'postgresql', mail, name,
            section, directory=directory)
        for to_remove in repos_to_remove:
            utils.remove_dir(to_remove, quiet=True)

    run("rm -Rf %s" % directory)


@task()
def clean(force=True):
    scm.prefetch(force=force)


@task()
def setup(branch='default', development=False, force=True):
    scm.hg_update('config', 'config', force, branch=branch)
    scm.update(clean=force)
    scm.fetch()
    scm.unknown(remove=True, quiet=force)


TestCollection = Collection()
TestCollection.add_task(test)
TestCollection.add_task(clean)
TestCollection.add_task(setup)
TestCollection.add_task(runtests)
TestCollection.add_task(runall)
