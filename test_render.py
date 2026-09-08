#!/usr/bin/env python
"""Test template rendering"""
import os
import sys
os.chdir(r"C:\Users\R\Documents\TA Machine Learning - Deteksi Kerusakan Jalan Real-Time")
sys.path.insert(0, os.getcwd())

from web.app import create_app

app = create_app()
with app.test_request_context('/'):
    from flask import render_template
    try:
        result = render_template('dashboard/disposisi_detail.html', 
            active='disposisi', 
            daerah='bogor', 
            item={
                'bap_nomor':'TEST',
                'lokasi':'Test',
                'waktu':'2026-01-01',
                'lat':None,
                'lon':None,
                'worst':'Berat',
                'total_rp':100000,
                'n_temuan':5,
                'urgensi':'Kritis',
                'instansi_nama':'Dinas',
                'status':'Terkirim',
                'id':1
            })
        print('RENDER OK, length:', len(result))
    except Exception as e:
        print('RENDER ERROR:', type(e).__name__, str(e)[:500])
