#
# How do we map from Big Blue Button user names to UNIX usernames?
#
# This version of that code (not currently used) uses a SQL table to
# map from BBB fullNames to the UNIX usernames or RFB ports they
# connect to:
#
# CREATE TABLE VNCusers(VNCuser text NOT NULL, UNIXuser text, rfbport integer, PRIMARY KEY (VNCuser));
#
# We access the database using some hard-wired parameters.  Create the
# 'vnc' user with something like this:
#
# CREATE ROLE vnc LOGIN PASSWORD 'vnc';
#
# GRANT SELECT ON VNCusers to vnc;

import psycopg2

postgreshost = 'localhost'
postgresdb = 'greenlight_production'
postgresuser = 'vnc'
postgrespw = 'vnc'

def fullName_to_UNIX_username(fullName):
    r"""
    Use a SQL table lookup to convert a Big Blue Button fullName
    into a UNIX username.
    """
    open_database()
    if conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT UNIXuser FROM VNCusers WHERE VNCuser = %s", (fullName,))
                row = cur.fetchone()
                if row:
                    return row[0]
            except psycopg2.DatabaseError as err:
                print(err)
                cur.execute('ROLLBACK')
    return None

def fullName_to_rfbport(fullName):
    r"""
    Use a SQL table lookup to convert a Big Blue Button fullName
    into a UNIX username.
    """
    open_database()
    if conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT rfbport FROM VNCusers WHERE VNCuser = %s", (fullName,))
                row = cur.fetchone()
                if row:
                    return row[0]
            except psycopg2.DatabaseError as err:
                print(err)
                cur.execute('ROLLBACK')
    return None

def UNIX_username_to_fullName(UNIXname):
    r"""
    Use a SQL table lookup to convert a UNIX username
    to a Big Blue Button fullName
    """
    open_database()
    if conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT VNCuser FROM VNCusers WHERE UNIXuser = %s", (UNIXname,))
                row = cur.fetchone()
                if row:
                    return row[0]
            except psycopg2.DatabaseError as err:
                print(err)
                cur.execute('ROLLBACK')
    return None
