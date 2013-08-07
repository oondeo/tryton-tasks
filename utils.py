import psycopg2
from invoke import task, run


@task
def update_parent_left_right(database, table, field, host='localhost',
    port='5432', user='angel', password='angel'):
    def _parent_store_compute(cr, table, field):
            def browse_rec(root, pos=0):
                where = field + '=' + str(root)

                if not root:
                    where = parent_field + 'IS NULL'

                cr.execute('SELECT id FROM %s WHERE %s \
                    ORDER BY %s' % (table, where, field))
                pos2 = pos + 1
                childs = cr.fetchall()
                for id in childs:
                    pos2 = browse_rec(id[0], pos2)
                cr.execute('update %s set "left"=%s, "right"=%s\
                    where id=%s' % (table, pos, pos2, root))
                return pos2 + 1

            query = 'SELECT id FROM %s WHERE %s IS NULL order by %s' % (
                table, field, field)
            pos = 0
            cr.execute(query)
            for (root,) in cr.fetchall():
                pos = browse_rec(root, pos)
            return True


    db = psycopg2.connect(dbname=database, host=host, port=port, user=user,
        password=password)

    print "calculating parent_left of table", table, "and field:", field
    _parent_store_compute(db.cursor(), table, field)



