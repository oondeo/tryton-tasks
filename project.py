#!/usr/bin/env python
import os
import sys

from invoke import task, Collection

from .config import get_config
from . import reviewboard
from .scm import get_branch
from .utils import t
import logging

try:
    from proteus import config as pconfig, Model
except ImportError, e:
    print >> sys.stderr, "trytond importation error: ", e

os.environ['TZ'] = "Europe/Madrid"
settings = get_config()

logger = logging.getLogger("nan-tasks")


def get_tryton_connection():
    tryton = settings['tryton']
    return pconfig.set_xmlrpc(tryton['server'])


@task
def ct(log_file):
    get_tryton_connection()
    create_test_task(log_file)


def create_test_task(log_file):

    get_tryton_connection()
    settings = get_config()
    tryton = settings['tryton']

    Project = Model.get('project.work')
    Employee = Model.get('company.employee')
    Party = Model.get('party.party')
    Tracker = Model.get('project.work.tracker')
    employee = Employee(int(tryton.get('default_employee_id')))
    parent = Project(int(tryton.get('default_project_id')))
    party = Party(int(tryton.get('default_party_id')))
    tracker = Tracker(int(tryton.get('default_tracker_id')))

    f = open(log_file, 'r')
    lines = []
    for line in f.readlines():
        if 'init' in line or 'modules' in line:
            continue
        lines.append(line)
    f.close()

    work = Project()
    work.type = 'task'
    work.product = None
    work.timesheet_work_name = 'Test Exception'
    work.parent = parent
    work.tracker = tracker
    work.party = party
    work.problem = "\n".join(lines)
    work.assigned_employee = employee
    work.save()


@task()
def tasks(party=None, user=None):
    get_tryton_connection()

    Project = Model.get('project.work')
    domain = [('state', '=', 'opened')]

    if party:
        domain.append(('party.name', 'ilike', "%" + party + "%"))
    if user:
        domain.append(('assigned_employee', 'ilike', "%" + user + "%"))

    projects = Project.find(domain)
    for project in projects:
        print "(%s) %s - (%s) %s [%s]" % (
            project.assigned_employee and project.assigned_employee.rec_name,
            project.rec_name,
            project.effort,
            project.task_phase.name,
            project.party.rec_name)


@task()
def close_review(work):
    get_tryton_connection()
    Review = Model.get('project.work.codereview')
    reviews = Review.find([('work.code', '=', work)])
    for review in reviews:
        reviewboard.close(review.review_id)


@task()
def fetch_reviews(branch='default', component=None, exclude_components=None):
    _fetch_reviews(branch, component, exclude_components)


def _fetch_reviews(branch='default', component=None, exclude_components=None):
    get_tryton_connection()
    Review = Model.get('project.work.codereview')
    reviews = Review.find([
            ('state', '=', 'opened'),
            ('branch', '=', branch),
            ])
    if not exclude_components:
        exclude_components = []
    for review in reviews:
        if component and review.component and \
                review.component.name != component:
            continue
        if review.component and review.component.name in exclude_components:
            continue
        if review.component:
            path = os.path.join('modules', review.component.name)
        else:
            path = ''
        try:
            reviewboard.fetch(path, review.review_id)
        except:
            logger.exception("Exception has occured", exc_info=1)


@task()
def fetch_review(work):
    get_tryton_connection()
    Review = Model.get('project.work.codereview')
    reviews = Review.find([('work.code', '=', work), ('state', '=', 'opened')])
    for review in reviews:
        if review.component:
            path = os.path.join('modules', review.component.name)
        else:
            path = ''
        if not os.path.exists(path):
            os.makedirs(path)

        reviewboard.fetch(path, review.review_id)


@task()
def upload_review(work, path, review=None):
    get_tryton_connection()
    Review = Model.get('project.work.codereview')
    Task = Model.get('project.work')
    Component = Model.get('project.work.component')

    tasks = Task.find([('code', '=', work)])
    if not tasks:
        print >>sys.stderr, t.red('Error: Task %s was not found.' % work)
        sys.exit(1)
    task = tasks[0]

    module = path.split('/')[-1]
    components = Component.find([('name', '=', module)])
    if not components:
        component = Component(name=module)
        component.save()
    else:
        component = components[0]

    review_id = reviewboard.create(path, task.rec_name,
        task.comment, task.code, review)

    review = Review.find([('review_id', '=', str(review_id))])
    if not review:
        review = Review()
    else:
        review = review[0]

    review.name = task.rec_name + "(" + module + ")"
    review.review_id = str(review_id)
    review.url = 'http://git.nan-tic.com/reviews/r/%s' % review_id
    review.work = task
    review.branch = get_branch(path)
    review.component = component
    review.save()


ProjectCollection = Collection()
ProjectCollection.add_task(upload_review)
ProjectCollection.add_task(fetch_review)
ProjectCollection.add_task(close_review)
ProjectCollection.add_task(tasks)
ProjectCollection.add_task(ct)
