#!/usr/bin/env python
from invoke import Collection, task, run
import hgapi
import git
import os
import sys
import subprocess
from blessings import Terminal
from multiprocessing import Process
from path import path
from .utils import _ask_ok

from .utils import t, read_config_file, NO_MODULE_REPOS

MAX_PROCESSES = 20

DEFAULT_BRANCH = {
    'git': 'master',
    'hg': 'default'
    }

MASTER_REVISION = {
    'git': 'master',
    'hg': 'tip',
}


def get_repo(section, config, function=None, development=False):
    repository = {}
    repository['type'] = config.get(section, 'repo')
    repository['url'] = config.get(section, 'url')
    repository['path'] = os.path.join(config.get(section, 'path'), section)
    repository['branch'] = DEFAULT_BRANCH[repository['type']]
    repository['revision'] = MASTER_REVISION[repository['type']]
    if config.has_option(section, 'revision') and \
            config.get(section, 'revision') and not development:
        repository['revision'] = config.get(section, 'revision')
    if config.has_option(section, 'branch'):
        repository['branch'] = config.get(section, 'branch')
    repository['function'] = None
    if function:
        repository['function'] = eval("%s_%s" % (repository['type'], function))
    return repository


def get_virtualenv():
    if os.environ.get('VIRTUAL_ENV'):
        return ''
    return os.path.join(os.path.dirname(__file__), 'virtual-env.sh')


@task()
def add2virtualenv():
    virtualenv = get_virtualenv()
    aux = run(virtualenv + ' lssitepackages')
    Config = read_config_file()
    for section in Config.sections():
        if not Config.has_option(section, 'add2virtualenv'):
            continue
        repo_path = Config.get(section, 'path')
        project_path = os.path.dirname(__file__).split('tasks')[-1]
        abspath = os.path.join(project_path, repo_path, section)
        if not abspath in str(aux):
            run(virtualenv + ' add2virtualenv ' + abspath, warn=True)


@task()
def repo_list(config=None, gitOnly=False, unstable=True, verbose=False):
    Config = read_config_file(config, unstable=unstable)

    repos = {
        'git': [],
        'hg': []
    }
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        url = Config.get(section, 'url')
        repo_path = Config.get(section, 'path')
        repos[repo] += [(section, url, repo_path)]

    if gitOnly:
        del repos['hg']

    for key, values in repos.iteritems():
        print >> sys.stderr, "Repositories in  " + t.bold(key)
        for val in values:
            name, url, repo_path = val
            if not verbose:
                print >> sys.stderr, name
            else:
                print >> sys.stderr, name, repo_path, url


@task()
def unknown(unstable=True, status=False, show=True):
    """
    Return a list of modules/repositories that exists in filesystem but not in
    config files
    ;param status: show status for unknown repositories.
    """
    Config = read_config_file(unstable=unstable)
    configs_module_list = [section for section in Config.sections()
        if section not in NO_MODULE_REPOS]

    modules_wo_repo = []
    repo_not_in_cfg = []
    for module_path in path('./modules').dirs():
        module_name = module_path.basename()
        if module_name in configs_module_list:
            continue

        if (module_path.joinpath('.hg').isdir() or
                module_path.joinpath('.git').isdir()):
            repo_not_in_cfg.append(module_name)
            if status and module_path.joinpath('.hg').isdir():
                hg_status(module_name, module_path.parent, False, None)
            elif status and module_path.joinpath('.git').isdir():
                git_status(module_name, module_path.parent, False, None)
        else:
            modules_wo_repo.append(module_name)

    if show:
        if modules_wo_repo:
            print t.bold("Unknown module (without repository):")
            print "  - " + "\n  - ".join(modules_wo_repo)
            print ""
        if not status and repo_not_in_cfg:
            print t.bold("Unknown repository:")
            print "  - " + "\n  - ".join(repo_not_in_cfg)
            print ""
    return modules_wo_repo, repo_not_in_cfg


def wait_processes(processes, maximum=MAX_PROCESSES):
    i = 0
    while len(processes) > maximum:
        if i >= len(processes):
            i = 0
        p = processes[i]
        p.join(0.1)
        if p.is_alive():
            i += 1
        else:
            del processes[i]


def hg_clone(url, path, branch="default", revision="tip"):
    command = 'hg clone -b %s -q %s %s -r %s' % (branch, url, path, revision)
    try:
        run(command)
    except:
        print >> sys.stderr, "Error running " + t.bold(command)
        raise
    print "Repo " + t.bold(path) + t.green(" Cloned") + \
        " to Revision:" + revision


def git_clone(url, path, branch="master", revision="master"):
    command = 'git clone -b %s -q %s %s' % (branch, url, path)
    if not path.endswith(os.path.sep):
        path += os.path.sep
    try:
        run(command)
        # Create .hg directory so hg diff on trytond does not
        # show git repositories.
        run('mkdir %s.hg' % path)
    except:
        print >> sys.stderr, "Error running " + t.bold(command)
        raise
    print "Repo " + t.bold(path) + t.green(" Cloned")


@task()
def clone(config=None, unstable=True, development=False):
    # Updates config repo to get new repos in config files
    hg_pull('config', '.', True)

    Config = read_config_file(config, unstable=unstable)
    p = None
    processes = []
    for section in Config.sections():
        repo = get_repo(section, Config, 'clone', development)
        if not os.path.exists(repo['path']):
            p = Process(target=repo['function'], args=(repo['url'],
                    repo['path'], repo['branch'], repo['revision']))
            p.start()
            processes.append(p)
            wait_processes(processes)
    wait_processes(processes, 0)


def print_status(module, files):
    status_key_map = {
        'A': 'Added',
        'M': 'Modified',
        'R': 'Removed',
        '!': 'Deleted',
        '?': 'Untracked',
        'D': 'Deleted',
    }

    status_key_color = {
        'A': 'green',
        'M': 'yellow',
        'R': 'red',
        '!': 'red',
        '=': 'blue',
        'D': 'red',
        '?': 'red',
    }

    msg = []
    for key, value in files.iteritems():
        tf = status_key_map.get(key)
        col = eval('t.' + status_key_color.get(key, 'normal'))
        for f in value:
            msg.append(col + " %s (%s):%s " % (tf, key, f) + t.normal)
    if msg:
        msg.insert(0, "[%s]" % module)
        print '\n'.join(msg)


def hg_status(module, path, verbose, url):
    repo = hgapi.Repo(path)
    actual_url = str(repo.config('paths', 'default')).rstrip('/')
    url = str(url).rstrip('/')
    if actual_url != url:
        print >> sys.stderr, (t.bold('[%s]' % module) +
            t.red(' URL differs: ') + t.bold(actual_url + ' != ' + url))
    msg = []
    if actual_url != url:
        msg.append(t.red("Repo URL differs: ")
            + t.bold(actual_url + " != " + url))

    st = repo.hg_status(empty=True)
    print_status(module, st)
    return st


def git_status(module, path, verbose, url):
    repo = git.Repo(path)
    config = repo.config_reader()
    config.read()
    actual_url = config.get_value('remote "origin"', 'url')
    if actual_url != url:
        print >> sys.stderr, (t.bold('[%s]' % module) +
            t.red(' URL differs: ') + t.bold(actual_url + ' != ' + url))
    diff = repo.index.diff(None)
    files = {}
    for change in diff.change_type:
        files[change] = []

    if diff:
        for change in diff.change_type:
            for d in diff.iter_change_type(change):
                files[change].append(d.a_blob.path)
    print_status(module, files)
    return files


@task
def status(config=None, unstable=True, no_quilt_pop=False, verbose=False):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    if not no_quilt_pop:
    	run('quilt pop -fa > /dev/null')
    for section in Config.sections():
        repo = get_repo(section, Config, 'status')
        if not os.path.exists(repo['path']):
            print >> sys.stderr, t.red("Missing repositori: ") +\
                    t.bold(repo['path'])
            return
        p = Process(target=repo['function'], args=(section,
                repo['path'], verbose, repo['url']))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)
    if not no_quilt_pop:
    	run('quilt push -fa > /dev/null')


def hg_resolve(module, path, verbose, action, tool, nostatus, include,
        exclude):
    repo_path = os.path.join(path, module)
    if not os.path.exists(repo_path):
        print >> sys.stderr, t.red("Missing repositori: ") + t.bold(repo_path)
        return

    assert action and action in ('merge', 'mark', 'unmark', 'list'), (
        "Invalid 'action' parameter for 'resolve': %s\nIt must to be 'merge', "
        "'list', 'mark', or 'unmark'." % action)

    repo = hgapi.Repo(repo_path)

    cmd = ['resolve']
    if action != 'merge':
        cmd.append('--%s' % action)
        if action == 'list':
            if nostatus:
                cmd.append('--no-status')
    else:
        if tool:
            assert tool in ('internal:dump', 'internal:fail', 'internal:local',
                'internal:merge', 'internal:other', 'internal:prompt'), (
                    "Invalid 'tool' parameter for 'resolve'. Look at "
                    "'hg help merge-tools' to know which tools are available.")
            cmd += ['-t', tool]
    if not include and not exclude:
        cmd.append('--all')
    else:
        if include:
            for pattern in include.split(','):
                cmd += ['-I', pattern]
        if exclude:
            for pattern in exclude.split(','):
                cmd += ['-X', pattern]

    try:
        out = repo.hg_command(*cmd)
    except hgapi.HgException, e:
        print t.bold_red('[' + module + ']')
        print "Error running %s (%s): %s" % (t.bold(*cmd), e.exit_code, str(e))
        return
    if out:
        print t.bold("= " + module + " =")
        print out


@task
def resolve(config=None, unstable=True, verbose=False, action='merge',
        tool=None, nostatus=False, include=None, exclude=None):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        if repo == 'hg':
            func = hg_resolve
        else:
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=func, args=(section, path, verbose, action, tool,
                nostatus, include, exclude))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_stat(path):
    result = run('cd %s; hg diff --stat' % path, hide=True)
    lines = result.stdout.split('\n')[:-2]
    files = []
    for line in lines:
        files.append(line.split('|')[0].strip())
    return files


def git_stat(path):
    print "git_stat not implemented yet"


@task
def stat(module):
    Config = read_config_file()
    for section in Config.sections():
        if section != module:
            continue
        repo = get_repo(section, Config, 'stat')
        return repo['function'](repo['path'])


def git_base_diff(path):
    print "git_base_diff not implemented yet"


def get_branch(path):
    branch = run('cd %s; hg branch' % path, hide=True)
    branch = branch.stdout.split('\n')[0]
    return branch


def hg_base_diff(path):
    files = " ".join(hg_stat(path))
    branch = get_branch(path)
    diff = run('cd %s; hg diff --git %s ' % (path, files), hide=True)
    base_diff = run('cd %s; hg diff --git -r null:%s  %s' % (path, branch,
        files), hide=True, warn=True)
    return diff.stdout, base_diff.stdout


@task
def module_diff(path, base=True, show=True, fun=hg_base_diff):
    diff, base_diff = fun(path)
    if show:
        print t.bold(path + " module diff:")
        if diff:
            print diff
        print t.bold(path + " module base diff:")
        if base_diff:
            print base_diff
        print ""
    return diff, base_diff


def git_diff(module, path, verbose, rev1, rev2):
    print "Git diff not implented"


def hg_diff(module, path, verbose, rev1, rev2):
    t = Terminal()
    try:
        msg = []
        path_repo = path
        if not os.path.exists(path_repo):
            print >> sys.stderr, (t.red("Missing repositori:")
                + t.bold(path_repo))
            return

        if not verbose:
            result = run('cd %s;hg diff --stat' % path_repo, hide='stdout')
            if result.stdout:
                msg.append(t.bold(module + "\n"))
                msg.append(result.stdout)
                print "\n".join(msg)
            return
        repo = hgapi.Repo(path_repo)
        if rev2 is None:
            rev2 = get_branch(path_repo)
        msg = []
        for diff in repo.hg_diff(rev1, rev2):
            if diff:
                d = diff['diff'].split('\n')
                for line in d:
                    if line and line[0] == '-':
                        line = t.red + line + t.normal
                    elif line and line[0] == '+':
                        line = t.green + line + t.normal

                    if line:
                        msg.append(line)
        if msg == []:
            return
        msg.insert(0, t.bold('\n[' + module + "]\n"))
        print "\n".join(msg)
    except:
        msg.insert(0, t.bold('\n[' + module + "]\n"))
        msg.append(str(sys.exc_info()[1]))
        print >> sys.stderr, "\n".join(msg)


@task
def diff(config=None, unstable=True, verbose=True, rev1=None, rev2=None):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    for section in Config.sections():
        repo = get_repo(section, Config, 'diff')
        p = Process(target=repo['function'], args=(section, repo['path'],
                verbose, rev1, rev2))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_compare_branches(module, path, first_branch, second_branch):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)
    #Shows all commits from the last point where both branches converged
    revisions = "'max(ancestor(%s, %s)):tip'" % (first_branch, second_branch)
    cmd = ['hg', 'log', '-r', revisions, '--template',
        "'{branch} ### {desc}\n'"]
    result = run(' '.join(cmd), warn=True, hide='both')
    commits = {
        first_branch: [],
        second_branch: [],
        }
    for line in result.stdout.split('\n'):
        try:
            branch, desc = line.split(' ### ')
        except ValueError:
            continue
        #Skip branch commits
        if 'branch' in desc.lower():
            continue
        if not branch in commits:
            continue
        commits[branch].append(desc)

    printed_header = False
    for desc in commits[first_branch]:
        if desc in commits[second_branch]:
            continue
        if not printed_header:
            printed_header = True
            print t.bold("= " + module + ": Missing commits on Branch "
                + first_branch + "=")
        print desc

    os.chdir(cwd)


@task
def compare_branches(first_branch, second_branch, config=None, unstable=True):
    '''
    Finds commits that exist on first branch but doesn't exist on
    second_branch. In order to identify a commit, its description is used as
    the revision_id may change when grafting commits from branches
    '''
    Config = read_config_file(config, unstable=unstable)
    processes = []
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        if repo == 'git':
            continue
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=hg_compare_branches, args=(section, path,
                first_branch, second_branch))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_summary(module, path, verbose):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return
    repo = hgapi.Repo(path_repo)
    cmd = ['summary', '--remote']
    summary = repo.hg_command(*cmd)
    print t.bold("= " + module + " =")
    print summary


@task
def summary(config=None, unstable=True, verbose=False):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_summary
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=func, args=(section, path, verbose))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_outgoing(module, path, verbose):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return
    repo = hgapi.Repo(path_repo)
    cmd = ['outgoing']
    if verbose:
        cmd.append('-v')

    try:
        out = repo.hg_command(*cmd)
    except hgapi.HgException, e:
        if 'no changes found' in str(e):
            return
        print t.bold_red('[' + module + ']')
        print "Error running %s (%s): %s" % (t.bold(*cmd), e.exit_code, str(e))
        return
    if out:
        print t.bold("= " + module + " =")
        print out


@task
def outgoing(config=None, unstable=True, verbose=False):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_outgoing
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=func, args=(section, path, verbose))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_pull(module, path, update, quiet=False, branch='default',
        revision='tip'):

    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)

    cmd = ['hg', 'pull', '-b', branch, '-r', revision]

    if update:
        cmd.append('-u')
        cmd.append('-y')  # noninteractive
    if quiet:
        cmd.append('-q')  # quiet

    print ' '.join(cmd)
    result = run(' '.join(cmd), warn=True ) #, hide='both')

    if not result.ok:
        print >> sys.stderr, t.red("= " + module + " = KO!")
        print >> sys.stderr, result.stderr
        os.chdir(cwd)
        return

    if "no changes found" in result.stdout:
        os.chdir(cwd)
        return

    print t.bold("= " + module + " =")
    print result.stdout
    os.chdir(cwd)


def git_pull(module, path, update):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)

    cmd = ['git', 'pull']
    result = run(' '.join(cmd), warn=True, hide='both')

    if not result.ok:
        print >> sys.stderr, t.red("= " + module + " = KO!")
        print >> sys.stderr, result.stderr
        os.chdir(cwd)
        return

    # If mercurial outputs 'no changes found'
    # or git outputs 'Already up-to-date' do not print anything.
    if ('no changes found' in result.stdout
            or 'Already up-to-date' in result.stdout):
        os.chdir(cwd)
        return

    print t.bold("= " + module + " =")
    print result.stdout
    os.chdir(cwd)


def hg_clean(module, path, url, force=False):
    st = hg_status(module, path, False, url)
    if st != {}:
        if not _ask_ok(
            'Answer "yes" to clean the "%s" repository '
                'in "%s" directory. [y/N] ' % (module, path), 'n'):
            return
        run('cd %s;hg update -C -y' % path, hide='stdout')


@task()
def clean(force=False, config=None, unstable=True):
    print t.bold('Reverting patches...')
    bashCommand = ['quilt', 'pop', '-fa']
    output, err = execBashCommand(bashCommand)
    Config = read_config_file(config, unstable=unstable)
    for section in Config.sections():
        repo = get_repo(section, Config, 'clean')
        repo['function'](section, repo['path'], repo['url'])

    print t.bold('Apply patches...')
    bashCommand = ['quilt', 'push', '-f']


@task()
def branch(branch, clean=False, config=None, unstable=True):
    if not branch:
        print >> sys.stderr, t.red("Missing required branch parameter")
        return

    print t.bold('Reverting patches...')
    bashCommand = ['quilt', 'pop', '-fa']
    output, err = execBashCommand(bashCommand)
    Config = read_config_file(config, unstable=unstable)

    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        if repo == 'git':
            continue
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=hg_update, args=(section, path, clean, branch))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)

    print t.bold('Applying patches...')
    bashCommand = ['quilt', 'push', '-a']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to apply patche(es)"
        print err


def hg_missing_branch(module, path, branch_name, closed=True):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)
    cmd = ['hg', 'branches']
    if closed:
        cmd.append('-c')
    result = run(' '.join(cmd), warn=True, hide='both')
    if branch_name not in result.stdout:
        print t.bold(module) + " misses branch %s" % branch_name
    os.chdir(cwd)


@task()
def missing_branch(branch_name, config=None, unstable=True):
    '''
    List all modules doesn't containt a branch named branc_name
    '''
    if not branch_name:
        print >> sys.stderr, t.red("Missing required branch parameter")
        return

    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        if repo == 'git':
            continue
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=hg_missing_branch, args=(section, path,
                branch_name))
        p.start()
        processes.append(p)
        wait_processes(processes)


def hg_create_branch(module, path, branch_name):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)

    cmd = ['hg', 'branches']
    result = run(' '.join(cmd), warn=True, hide='both')
    if branch_name not in result.stdout:
        cmd = ['hg', 'branch', branch_name]
        result = run(' '.join(cmd), warn=True, hide='both')
        cmd = ['hg', 'commit', '-m', '"Create branch ' + branch_name + '"']
        result = run(' '.join(cmd), warn=True, hide='both')

    os.chdir(cwd)


@task()
def create_branch(branch_name, config=None, unstable=True):
    '''
    Create a branch with name branch_name to all the repositories that don't
    contain a branch with the same name.

    WARNING: This will clear all the uncommited changes in order to not
    add this changes to the new branch.
    '''
    if not branch_name:
        print >> sys.stderr, t.red("Missing required branch parameter")
        return

    print t.bold('Reverting patches...')
    bashCommand = ['quilt', 'pop', '-fa']
    output, err = execBashCommand(bashCommand)
    print t.bold('Cleaning all changes...')
    Config = read_config_file(config, unstable=unstable)
    update(config, unstable=True, clean=True)
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        if repo == 'git':
            continue
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=hg_create_branch, args=(section, path, branch_name))
        p.start()
        processes.append(p)
        wait_processes(processes)

    print t.bold('Applying patches...')
    bashCommand = ['quilt', 'push', '-a']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to apply patche(es)"
        print err


@task
def pull(config=None, unstable=True, update=True, development=False):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = get_repo(section, Config, 'pull', development)
        p = Process(target=repo['function'], args=(section, repo['path'],
            update, repo['revision']))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_push(module, path, url, new_branches=False):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)

    cmd = ['hg', 'push', url]
    if new_branches:
        cmd.append('--new-branch')
    result = run(' '.join(cmd), warn=True, hide='both')

    print t.bold("= " + module + " =")
    print result.stdout
    os.chdir(cwd)


@task
def push(config=None, unstable=True, new_branches=False):
    '''
    Pushes all pending commits to the repo url.

    url that start with http are excluded.
    '''
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        #Don't push to repos that start with http as we don't have access to
        url = Config.get(section, 'url')
        if url[:4] == 'http':
            continue
        if repo == 'hg':
            func = hg_push
        elif repo == 'git':
            continue
        else:
            print >> sys.stderr, "Not developed yet"
            continue
        p = Process(target=func, args=(section, path, url, new_branches))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def hg_update(module, path, clean, branch=None):
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cwd = os.getcwd()
    os.chdir(path_repo)

    cmd = ['hg', 'update']
    if clean:
        cmd.append('-C')
    else:
        cmd.append('-y')  # noninteractive

    if branch:
        cmd.extend(['-r', branch])
    result = run(' '.join(cmd), warn=True, hide='both')

    if not result.ok:
        if branch is not None and u'abort: unknown revision' in result.stderr:
            os.chdir(cwd)
            return
        print >> sys.stderr, t.red("= " + module + " = KO!")
        print >> sys.stderr, result.stderr
        os.chdir(cwd)
        return

    if (u"0 files updated, 0 files merged, 0 files removed, 0 "
            u"files unresolved\n") in result.stdout:
        os.chdir(cwd)
        return

    print t.bold("= " + module + " =")
    print result.stdout
    os.chdir(cwd)


@task
def update(config=None, unstable=True, clean=False):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        repo = Config.get(section, 'repo')
        path = Config.get(section, 'path')
        func = hg_update
        if repo == 'git':
            continue
        if repo != 'hg':
            print >> sys.stderr, "Not developed yet"
            continue
        branch = None
        if clean:
            # Force branch only when clean is set
            branch = Config.get(section, 'branch')
        p = Process(target=func, args=(section, path, clean, branch))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def git_revision(module, path, verbose):
    print "Git revision not implented"


def hg_revision(module, path, verbose):
    t = Terminal()
    path_repo = path
    if not os.path.exists(path_repo):
        print >> sys.stderr, (t.red("Missing repositori:")
            + t.bold(path_repo))
        return False

    result = run('cd %s;hg parent --template "{rev}"' % path_repo,
        hide='stdout')
    if result.stdout:
        if verbose:
            print >> sys.stderr, t.bold(module) \
                + " revision:" + result.stdout
        return result.stdout
    return False


@task
def revision(config=None, unstable=True, verbose=True):
    Config = read_config_file(config, unstable=unstable)
    processes = []
    for section in Config.sections():
        repo = get_repo(section, Config, 'revision')
        p = Process(target=repo['function'], args=(section, repo['path'],
            verbose))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


@task()
def fetch():
    print t.bold('Reverting patches...')
    bashCommand = ['quilt', 'pop', '-fa']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to remove patche(es)"
        print err
        print t.bold('Not Fetched.')
        return
    print t.bold('Pulling and updated local repository...')
    bashCommand = ['hg', 'pull', '-u']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to pull the local repostory. Err:"
        print err
    print t.bold('Pulling...')
    pull()
    print t.bold('Updating...')
    update()
    print t.bold('Cloning...')
    clone()
    print t.bold('Applying patches...')
    bashCommand = ['quilt', 'push', '-a']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to apply patche(es)"
        print err
    print t.bold('Updating requirements...')
    bashCommand = ['pip', 'install', '-r', 'config/requirements.txt']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to apply patche(es)"
        print err
    bashCommand = ['pip', 'install', '-r', 'tasks/requirements.txt']
    output, err = execBashCommand(bashCommand)
    if not err:
        print output
    else:
        print "It's not possible to apply patche(es)"
        print err

    #print t.bold('Updating virtualenv paths...')
    #add2virtualenv()

    print t.bold('Fetched.')


def increase_module_version(module, path, version):
    '''
    Increase version of module
    Cred: http://hg.tryton.org/tryton-tools/file/5f31cfd7e596/increase_version
    '''
    path_repo = os.path.join(path, module)
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing repositori:") + t.bold(path_repo)
        return

    cfg_file = os.path.join(path_repo, 'tryton.cfg')
    if not os.path.exists(path_repo):
        print >> sys.stderr, t.red("Missing tryton.cfg file:") + t.bold(
            cfg_file)
        return

    def increase(line):
        if line.startswith('version='):
            return 'version=%s\n' % version
        return line

    cwd = os.getcwd()
    os.chdir(path_repo)

    content = ''
    filename = 'tryton.cfg'
    with open(filename) as fp:
        for line in fp:
            content += increase(line)
    with open(filename, 'w') as fp:
        fp.write(content)

    os.chdir(cwd)


@task
def increase_version(version, config=None, unstable=True, clean=False):
    '''
    Modifies all tryton.cfg files in order to set version to <version>
    '''
    if not version:
        print >> sys.stderr, t.red("Missing required version parameter")
        return
    Config = read_config_file(config, unstable=unstable)
    processes = []
    p = None
    for section in Config.sections():
        path = Config.get(section, 'path')
        p = Process(target=increase_module_version, args=(section, path,
                version))
        p.start()
        processes.append(p)
        wait_processes(processes)
    wait_processes(processes, 0)


def execBashCommand(bashCommand):
    """
        Execute bash command.
        @bashCommand: is list with the command and the options
        return: list with the output and the posible error
    """
    process = subprocess.Popen(bashCommand, stdout=subprocess.PIPE)
    output, err = process.communicate()
    return output, err


ScmCollection = Collection()
ScmCollection.add_task(clone)
ScmCollection.add_task(status)
ScmCollection.add_task(resolve)
ScmCollection.add_task(diff)
ScmCollection.add_task(summary)
ScmCollection.add_task(outgoing)
ScmCollection.add_task(push)
ScmCollection.add_task(pull)
ScmCollection.add_task(update)
ScmCollection.add_task(repo_list)
ScmCollection.add_task(fetch)
ScmCollection.add_task(unknown)
ScmCollection.add_task(stat)
ScmCollection.add_task(branch)
ScmCollection.add_task(missing_branch)
ScmCollection.add_task(create_branch)
ScmCollection.add_task(compare_branches)
ScmCollection.add_task(module_diff)
ScmCollection.add_task(add2virtualenv)
ScmCollection.add_task(increase_version)
ScmCollection.add_task(revision)
ScmCollection.add_task(clean)
