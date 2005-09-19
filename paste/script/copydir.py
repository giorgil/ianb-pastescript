import os
import string
import cgi
import urllib
import re
Cheetah = None

def copy_dir(source, dest, vars, verbosity, simulate, indent=0,
             use_cheetah=False, sub_vars=True, interactive=False):
    names = os.listdir(source)
    names.sort()
    pad = ' '*(indent*2)
    if not os.path.exists(dest):
        if verbosity >= 1:
            print '%sCreating %s/' % (pad, dest)
        if not simulate:
            os.makedirs(dest)
    elif verbosity >= 2:
        print '%sDirectory %s exists' % (pad, dest)
    for name in names:
        full = os.path.join(source, name)
        if name.startswith('.'):
            if verbosity >= 2:
                print '%sSkipping hidden file %s' % (pad, full)
            continue
        if sub_vars:
            dest_full = os.path.join(dest, substitute_filename(name, vars))
        sub_file = False
        if dest_full.endswith('_tmpl'):
            dest_full = dest_full[:-5]
            sub_file = sub_vars
        if os.path.isdir(full):
            if verbosity:
                print '%sRecursing into %s' % (pad, os.path.basename(full))
            copy_dir(full, dest_full, vars, verbosity, simulate,
                     indent=indent+1, use_cheetah=use_cheetah,
                     sub_vars=sub_vars, interactive=interactive)
            continue
        f = open(full, 'rb')
        content = f.read()
        f.close()
        if sub_file:
            content = substitute_content(content, vars, filename=full,
                                         use_cheetah=use_cheetah)
        if os.path.exists(dest_full):
            f = open(dest_full, 'rb')
            old_content = f.read()
            f.close()
            if old_content == content:
                if verbosity:
                    print '%s%s already exists (same content)' % (pad, dest_full)
                continue
            if interactive:
                if not query_interactive(
                    full, dest_full, content, old_content,
                    simulate=simulate):
                    continue
        if verbosity:
            print '%sCopying %s to %s' % (pad, os.path.basename(full), dest_full)
        if not simulate:
            f = open(dest_full, 'wb')
            f.write(content)
            f.close()

def query_interactive(src_fn, dest_fn, src_content, dest_content,
                      simulate):
    from difflib import unified_diff, context_diff
    u_diff = list(unified_diff(
        dest_content.splitlines(),
        src_content.splitlines(),
        dest_fn, src_fn))
    c_diff = list(context_diff(
        dest_content.splitlines(),
        src_content.splitlines(),
        dest_fn, src_fn))
    added = len([l for l in u_diff if l.startswith('+')
                   and not l.startswith('+++')])
    removed = len([l for l in u_diff if l.startswith('-')
                   and not l.startswith('---')])
    if added > removed:
        msg = '; %i lines added' % (added-removed)
    elif removed > added:
        msg = '; %i lines removed' % (removed-added)
    else:
        msg = ''
    print 'Replace %i bytes with %i bytes (%i/%i lines changed%s)' % (
        len(dest_content), len(src_content),
        removed, len(dest_content.splitlines()), msg)
    prompt = 'Overwrite %s [Y/n/d/b/?] ' % dest_fn
    while 1:
        response = raw_input(prompt).strip().lower()
        if not response or response[0] == 'y':
            return True
        elif response[0] == 'n':
            return False
        elif response == 'dc':
            print '\n'.join(c_diff)
        elif response[0] == 'd':
            print '\n'.join(u_diff)
        elif response[0] == 'b':
            import shutil
            new_dest_fn = dest_fn + '.bak'
            n = 0
            while os.path.exists(new_dest_fn):
                n += 1
                new_dest_fn = dest_fn + '.bak' + str(n)
            print 'Backing up %s to %s' % (dest_fn, new_dest_fn)
            if not simulate:
                shutil.copyfile(dest_fn, new_dest_fn)
            return True
        else:
            print query_usage

query_usage = """\
Responses:
  Y(es):    Overwrite the file with the new content.
  N(o):     Do not overwrite the file.
  D(iff):   Show a unified diff of the proposed changes (dc=context diff)
  B(ackup): Save the current file contents to a .bak file
            (and overwrite)
"""

def substitute_filename(fn, vars):
    for var, value in vars.items():
        fn = fn.replace('+%s+' % var, str(value))
    return fn

def substitute_content(content, vars, filename='<string>',
                       use_cheetah=False):
    global Cheetah
    if not use_cheetah:
        v = standard_vars.copy()
        v.update(vars)
        tmpl = LaxTemplate(content)
        try:
            return tmpl.substitute(TypeMapper(v))
        except Exception, e:
            _add_except(e, ' in file %s' % filename)
            raise
    if Cheetah is None:
        import Cheetah.Template
    tmpl = Cheetah.Template.Template(source=content, file=filename,
                                     searchList=[vars])
    return str(tmpl)

def html_quote(s):
    if s is None:
        return ''
    return cgi.escape(str(s), 1)

def url_quote(s):
    if s is None:
        return ''
    return urllib.quote(str(s))

def test(conf, true_cond, false_cond=None):
    if conf:
        return true_cond
    else:
        return false_cond

def _add_except(exc, info):
    if not hasattr(exc, 'args') or exc.args is None:
        return
    args = list(exc.args)
    args[0] += ' ' + info
    exc.args = tuple(args)
    return
    

standard_vars = {
    'nothing': None,
    'html_quote': html_quote,
    'url_quote': url_quote,
    'empty': '""',
    'test': test,
    'repr': repr,
    'str': str,
    'bool': bool,
    }

class TypeMapper(dict):

    def __getitem__(self, item):
        options = item.split('|')
        for op in options[:-1]:
            try:
                value = eval_with_catch(op, dict(self))
                break
            except (NameError, KeyError):
                pass
        else:
            value = eval(options[-1], dict(self))
        if value is None:
            return ''
        else:
            return str(value)

def eval_with_catch(expr, vars):
    try:
        return eval(expr, vars)
    except Exception, e:
        _add_except(e, 'in expression %r' % expr)
        raise
        
class LaxTemplate(string.Template):
    # This change of pattern allows for anything in braces, but
    # only identifiers outside of braces:
    pattern = re.compile(r"""
    \$(?:
      (?P<escaped>\$)             |   # Escape sequence of two delimiters
      (?P<named>[_a-z][_a-z0-9]*) |   # delimiter and a Python identifier
      {(?P<braced>.*?)}           |   # delimiter and a braced identifier
      (?P<invalid>)                   # Other ill-formed delimiter exprs
    )
    """, re.VERBOSE | re.IGNORECASE)
