import psycopg2 as pg

class conncur:
    def __init__(self, *args, **kwargs):
        self.conn = pg.connect(*args, **kwargs)
        self.cur = self.conn.cursor()
    def __enter__(self):
        return self.conn, self.cur
    def __exit__(self, type, value, traceback):
        self.cur.close()
        self.conn.close()


def setup_db(create=False):
    """ execute blocks of sql delimited by --words-- in the setup file
        first 4 blocks do user and database setup
        the following 3 blocks do schema and table creation and alters
    """
    with open('heatmap_db_setup.sql', 'rt') as f:
        lines = [' '+l.rstrip('\n').strip(' ') for l in f.readlines()]
    text = ''.join(lines)
    sql_blocks = [l.strip(' ') for l in text.split('--')][::2][1:]  #user, alter user, drop, db, tables, alter

    if create:
        with conncur(dbname='postgres',user='postgres', host='localhost', port=5432) as (conn, cur):
            for sql in sql_blocks[:4]:
                print(sql)
                if sql.startswith('DROP DATABASE') or sql.startswith('CREATE DATABASE') :
                    conn.set_isolation_level(0)
                    cur.execute(sql)
                    conn.commit()
                    conn.set_isolation_level(1)
                else:
                    cur.execute(sql)
                    conn.commit()

            with conncur(dbname='heatmap_test',user='postgres', host='localhost', port=5432) as (conn, cur):
                sql = sql_blocks[4]
                cur.execute(sql)
                conn.commit()

    with conncur(dbname='heatmap_test',user='heatmapadmin', host='localhost', port=5432) as (conn, cur):
        for sql in sql_blocks[5:8]:
            print(sql)
            cur.execute(sql)
            conn.commit()

def main():
    setup_db()

if __name__ == '__main__':
    main()
