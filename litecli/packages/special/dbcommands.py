import logging
import os
import platform
from sqlite3 import ProgrammingError

from litecli import __version__
from litecli.packages.special import iocommands
from litecli.packages.special.utils import format_uptime
from .main import special_command, RAW_QUERY, PARSED_QUERY

log = logging.getLogger(__name__)


@special_command('\\dt', '.tables[+] [table]', 'List or describe tables.',
                 arg_type=PARSED_QUERY, case_sensitive=True, aliases=('.tables',))
def list_tables(cur, arg=None, arg_type=PARSED_QUERY, verbose=False):
    if arg:
        args = ('{0}%'.format(arg),)
        query = '''
            SELECT name FROM sqlite_master
            WHERE type IN ('table','view') AND name LIKE ? AND name NOT LIKE 'sqlite_%'
            ORDER BY 1
        '''
    else:
        args = tuple()
        query = '''
            SELECT name FROM sqlite_master
            WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
            ORDER BY 1
        '''

    log.debug(query)
    cur.execute(query, args)
    tables = cur.fetchall()
    status = ''
    if cur.description:
        headers = [x[0] for x in cur.description]
    else:
        return [(None, None, None, '')]

    # if verbose and arg:
    #     query = "SELECT sql FROM sqlite_master WHERE name LIKE ?"
    #     log.debug(query)
    #     cur.execute(query)
    #     status = cur.fetchone()[1]

    return [(None, tables, headers, status)]


@special_command('.schema', '.schema[+] [table]', 'The complete schema for the database or a single table',
                 arg_type=PARSED_QUERY, case_sensitive=True)
def show_schema(cur, arg=None, **_):
    if arg:
        args = (arg,)
        query = '''
            SELECT sql FROM sqlite_master
            WHERE name==?
            ORDER BY tbl_name, type DESC, name
        '''
    else:
        args = tuple()
        query = '''
            SELECT sql FROM sqlite_master
            ORDER BY tbl_name, type DESC, name
        '''

    log.debug(query)
    cur.execute(query, args)
    tables = cur.fetchall()
    status = ''
    if cur.description:
        headers = [x[0] for x in cur.description]
    else:
        return [(None, None, None, '')]

    return [(None, tables, headers, status)]


@special_command('.databases', '.databases', 'List databases.', arg_type=RAW_QUERY, case_sensitive=True)
def list_databases(cur, **_):
    query = "PRAGMA database_list"
    log.debug(query)
    cur.execute(query)
    if cur.description:
        headers = [x[0] for x in cur.description]
        return [(None, cur, headers, '')]
    else:
        return [(None, None, None, '')]


@special_command('status', '\\s', 'Get status information from the server.',
                 arg_type=RAW_QUERY, aliases=('\\s', ), case_sensitive=True)
def status(cur, **_):
    query = 'SHOW GLOBAL STATUS;'
    log.debug(query)
    try:
        cur.execute(query)
    except ProgrammingError:
        # Fallback in case query fail, as it does with Mysql 4
        query = 'SHOW STATUS;'
        log.debug(query)
        cur.execute(query)
    status = dict(cur.fetchall())

    query = 'SHOW GLOBAL VARIABLES;'
    log.debug(query)
    cur.execute(query)
    variables = dict(cur.fetchall())

    # prepare in case keys are bytes, as with Python 3 and Mysql 4
    if (isinstance(list(variables)[0], bytes) and
            isinstance(list(status)[0], bytes)):
        variables = {k.decode('utf-8'): v.decode('utf-8') for k, v
                     in variables.items()}
        status = {k.decode('utf-8'): v.decode('utf-8') for k, v
                  in status.items()}

    # Create output buffers.
    title = []
    output = []
    footer = []

    title.append('--------------')

    # Output the litecli client information.
    implementation = platform.python_implementation()
    version = platform.python_version()
    client_info = []
    client_info.append('litecli {0},'.format(__version__))
    client_info.append('running on {0} {1}'.format(implementation, version))
    title.append(' '.join(client_info) + '\n')

    # Build the output that will be displayed as a table.
    output.append(('Connection id:', cur.connection.thread_id()))

    query = 'SELECT DATABASE(), USER();'
    log.debug(query)
    cur.execute(query)
    db, user = cur.fetchone()
    if db is None:
        db = ''

    output.append(('Current database:', db))
    output.append(('Current user:', user))

    if iocommands.is_pager_enabled():
        if 'PAGER' in os.environ:
            pager = os.environ['PAGER']
        else:
            pager = 'System default'
    else:
        pager = 'stdout'
    output.append(('Current pager:', pager))

    output.append(('Server version:', '{0} {1}'.format(
        variables['version'], variables['version_comment'])))
    output.append(('Protocol version:', variables['protocol_version']))

    if 'unix' in cur.connection.host_info.lower():
        host_info = cur.connection.host_info
    else:
        host_info = '{0} via TCP/IP'.format(cur.connection.host)

    output.append(('Connection:', host_info))

    query = ('SELECT @@character_set_server, @@character_set_database, '
             '@@character_set_client, @@character_set_connection LIMIT 1;')
    log.debug(query)
    cur.execute(query)
    charset = cur.fetchone()
    output.append(('Server characterset:', charset[0]))
    output.append(('Db characterset:', charset[1]))
    output.append(('Client characterset:', charset[2]))
    output.append(('Conn. characterset:', charset[3]))
    output.append(('Uptime:', format_uptime(status['Uptime'])))

    # Print the current server statistics.
    stats = []
    stats.append('Connections: {0}'.format(status['Threads_connected']))
    if 'Queries' in status:
        stats.append('Queries: {0}'.format(status['Queries']))
    stats.append('Slow queries: {0}'.format(status['Slow_queries']))
    stats.append('Opens: {0}'.format(status['Opened_tables']))
    stats.append('Flush tables: {0}'.format(status['Flush_commands']))
    stats.append('Open tables: {0}'.format(status['Open_tables']))
    if 'Queries' in status:
        queries_per_second = int(status['Queries']) / int(status['Uptime'])
        stats.append('Queries per second avg: {:.3f}'.format(
            queries_per_second))
    stats = '  '.join(stats)
    footer.append('\n' + stats)

    footer.append('--------------')
    return [('\n'.join(title), output, '', '\n'.join(footer))]
