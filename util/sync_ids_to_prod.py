#!/usr/bin/env python3
import json
from os import environ
from heatmaps.services import database_service, heatmap_service, summary_service, str_cast

class prodUpdate(database_service):
    dbname = "heatmap"
    #host = "postgres.neuinfo.org"  # should probably put this in environment variables as well 
    host = "DEADBEEF"  # protect yourself!
    user = "heatmapuser"
    port = 5432
    hstore = True

    def add_existing_heatmap_data(self, heatmap_data, filename, timestamp):
        sql_ins_term = "INSERT INTO term_history (term, term_counts) VALUES (%s,%s) RETURNING id;"
        th_ids = []
        for term in heatmap_data:
            ins_args = (term, str_cast(heatmap_data[term]))
            ti_result = self.cursor_exec(sql_ins_term, ins_args)
            th_id = ti_result[0][0]
            th_ids.append(th_id)

        sql_hp = "INSERT INTO heatmap_prov (filename, datetime) VALUES (%s,%s) RETURNING id, datetime"
        args = (filename, timestamp)
        [(hp_id, timestamp_new)] = self.cursor_exec(sql_hp, args)
        assert timestamp == timestamp_new, (timestamp, timestamp_new)

        sql_add_junc = b"INSERT INTO heatmap_prov_to_term_history VALUES "#(%s,%s)"
        hp_ids = [hp_id] * len(th_ids)
        junc_args = (hp_ids, th_ids)
        sql_values = b",".join(self.mogrify("(%s,%s)", tup) for tup in zip(*junc_args))
        self.cursor_exec(sql_add_junc + sql_values)

        self.conn.commit()

        return hp_id
        #return heatmap_data, hp_id, timestamp

orpheus_hmserv = heatmap_service(summary_service())  # heatmap_test database
prod_hmserv = prodUpdate()

def main():
    prov_pairs = [('orpheus_id','prod_id')]
    for orpheus_id in range(0,91):
        print(prod_id)  # in case something bad happens we know how far
        heatmap_data = orpheus_hmserv.get_heatmap_data_from_id(orpheus_id)
        if not heatmap_data:
            print('WARNING: heatmap with ID ', orpheus_id, 'not found! Skipping.')
            continue
        timestamp, filename = orpheus_hmserv.get_prov_from_id(orpheus_id, iso=False)
        prod_id = prod_hmserv.add_existing_heatmap_data(heatmap_data, filename, timestamp)
        prov_pairs.append((orpheus_id, prod_id))

    with open('orpheus_to_prod_sync.json.new', 'wt') as f:
        json.dump(prov_pairs, f)

if __name__ == '__main__':
    main()

