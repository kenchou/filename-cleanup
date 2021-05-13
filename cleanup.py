#!/usr/bin/env python

import click
import logging
import re
import yaml

from collections.abc import Mapping
from collections import OrderedDict
from fnmatch import fnmatch
from pathlib import Path
from typing import Pattern


logging.basicConfig()
logger = logging.getLogger('cleanup')
LOG_LEVEL = {
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}

space = '    '
branch = '│   '
tee = '├── '
last = '└── '

global_options = {}
statistics = {'removed': 0, 'renamed': 0, 'dir-total-count': 0, 'file-total-count': 0}
patterns = {
    'remove': [],
    'cleanup': [],
}
pending_list = {
    'remove': [],
    'cleanup': [],
    'normal': [],
}


def uniq_list_keep_order(seq):
    """get a uniq list and keep the elements order"""
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def guess_path(test_file, guess_paths=None):
    """test the file exists in one of guess paths"""
    if test_file is None:
        return
    test_file = Path(test_file).expanduser()
    if guess_paths is None:
        guess_paths = [
            Path.cwd(),  # current dir
            Path.home(),  # home dir
            Path(__file__).parent.parent,  # script dir
        ]
    for p in uniq_list_keep_order([Path(p).resolve() for p in guess_paths]):
        file_path = p / test_file
        if file_path.is_file():
            return file_path
    return


def load_patterns(filename):
    with open(filename, encoding="utf8") as f:
        config = yaml.safe_load(f)
    for line in config['remove'].splitlines():
        patterns['remove'].append(re.compile(line[1:], flags=re.IGNORECASE) if line.startswith('/') else line)
    for line in config['cleanup'].splitlines():
        patterns['cleanup'].append(re.compile(line, flags=re.IGNORECASE))


def match_remove_pattern(filename):
    for p in patterns['remove']:
        if isinstance(p, Pattern):
            matched = p.search(str(filename))
            pat = p.pattern
        else:
            matched = fnmatch(filename, p)
            pat = p
        if matched:
            return matched, pat
    else:
        return False, None


def clean_filename(filename):
    for p in patterns['cleanup']:
        filename = p.sub('', filename)
    return filename


def recursive_cleanup(target_path):
    enabled_remove = global_options['feature_remove']
    enabled_rename = global_options['feature_rename']

    t = Path(target_path)
    if '.tmp' == str(t.name):
        return

    if enabled_remove:
        matched, pat = match_remove_pattern(t.name)
        if matched:
            if t.is_dir() and not t.is_symlink():  # remove dir and all children
                children = [(x, None) for x in reversed(list(t.glob('**/*')))]
                pending_list['remove'].extend(children)
                statistics['removed'] += len(children)
                statistics['dir-total-count'] += len([1 for x, _ in children if x.is_dir()]) + 1
                statistics['file-total-count'] += len([1 for x, _ in children if not x.is_dir()])
            else:
                statistics['file-total-count'] += 1
            pending_list['remove'].append((t, pat))
            statistics['removed'] += 1
            return  # return early

    if t.is_dir() and not t.is_symlink():  # do not follow symlinks
        nodes = sorted(t.iterdir(), key=lambda f: (0 if f.is_dir() else 1, f.name))  # 目录优先/深度优先
        for item in nodes:
            recursive_cleanup(item)  # 递归遍历子目录, 深度优先
        statistics['dir-total-count'] += 1
    else:
        statistics['file-total-count'] += 1

    if enabled_rename:
        new_filename = clean_filename(t.name)
        if new_filename != t.name:
            statistics['renamed'] += 1
            pending_list['cleanup'].append((t, new_filename))
            return

    pending_list['normal'].append(t)


def get_badge(i):
    if i.is_dir():
        return 'cyan', '/'
    else:
        return 'green', ''


def path_list_to_tree_dict(path_list):
    tree = OrderedDict()
    for i in path_list:
        node = tree
        for p in i.parts:
            if p == i.name:
                if i.is_symlink():
                    node.setdefault(p, str(i.readlink()))  # leaf
                else:
                    node.setdefault(p, None)  # leaf
            else:
                node = node.setdefault(p, OrderedDict())  # sub-dir
    return tree


def tree_dict_iterator(dir_path, prefix=''):
    """A recursive generator, given a directory Path object
    will yield a visual tree structure line by line
    with each line prefixed by the same characters
    """
    contents = dir_path.keys()
    # contents each get pointers that are ├── with a final └── :
    pointers = [tee] * (len(contents) - 1) + [last]
    for pointer, path in zip(pointers, contents):
        node = dir_path[path]
        if isinstance(node, str):   # append symlink
            path += '@ -> ' + node
        yield prefix + pointer + path
        if isinstance(node, Mapping):  # extend the prefix and recurse:
            extension = branch if pointer == tee else space
            # i.e. space because last, └── , above so no more |
            yield from tree_dict_iterator(node, prefix=prefix + extension)


@click.command()
@click.argument('target-path', default='.')
@click.option('-c', '--config', 'cleanup_patterns_file', metavar='<PATTERNS-CONFIG-FILE>',
              help='yml config of cleanup patterns. '
                   'Default: search ".cleanup-patterns.yml" in [TARGET-PATH, **TARGET-PATH.PARENTS, $HOME, BIN-PATH]')
@click.option('-d/-D', '--remove/--no-remove', 'feature_remove', default=True,
              help='Remove (or not) files and directories which matched remove patterns. Default: --remove')
@click.option('-r/-R', '--rename/--no-rename', 'feature_rename', default=True,
              help='Rename (or not) files and directories which matched patterns. Default: --rename')
@click.option('-e/-E', '--empty/--no-empty', 'empty_remove', default=True,
              help='Remove empty dir. Default: --empty')
@click.option('--prune', is_flag=True, default=False,
              help='Execute remove and rename files and directories which matched clean patterns')
@click.option('-v', '--verbose', count=True,
              help='-v=info, -vv=debug')
def main(target_path, cleanup_patterns_file, feature_remove, feature_rename, empty_remove, prune, verbose):
    logger.setLevel(LOG_LEVEL[verbose] if verbose in LOG_LEVEL else logging.DEBUG)

    global_options['feature_remove'] = feature_remove
    global_options['feature_rename'] = feature_rename
    global_options['empty_remove'] = empty_remove
    global_options['prune'] = prune

    logger.debug(f'{global_options=}')

    target = Path(target_path)
    if not target.exists():
        click.secho(f'Target path "{target_path}" does not exists.', err=True)
        exit(1)

    # guess the config location
    if not cleanup_patterns_file:
        guess_paths = [target] + list(target.absolute().parents) + [
            Path.home(),
            Path(__file__).resolve().parent,  # ${BIN_PATH}/.aria2/
        ]
        cleanup_patterns_file = guess_path('.cleanup-patterns.yml', guess_paths)

    # load patterns from config
    if cleanup_patterns_file:
        logger.info(f"{cleanup_patterns_file=}")
        load_patterns(cleanup_patterns_file)

    # recursive scan the target dir
    recursive_cleanup(target)

    # cleanup
    if pending_list['remove'] or pending_list['cleanup']:
        click.echo("\n--- Summary ---")

    # remove junk files
    if feature_remove:
        for i, pat in pending_list['remove']:
            click.secho('[-] ', fg='red', nl=False)

            color, trailing_slash = get_badge(i)
            if not pat:
                color = None
            click.echo(f'{i.parent}/', nl=False)
            click.secho(f'{i.name}{trailing_slash}', fg=color, nl=False)
            click.echo(f' <= {pat}' if verbose >= 3 and pat else '')
            if prune:
                # do not follow symlink
                if i.is_dir() and not i.is_symlink():
                    i.rmdir()
                    if empty_remove and not any(i.iterdir()):   # remove empty dir
                        i.unlink()
                else:
                    i.unlink()

    # clean/rename filename
    if feature_rename:
        for i, new_filename in pending_list['cleanup']:
            click.secho('[*] ', fg='yellow', nl=False)

            color, trailing_slash = get_badge(i)
            old = click.style(i.name, fg=color)
            new = click.style(new_filename, fg='yellow')
            click.echo(f'{i.parent}/{{ "{old}" => "{new}" }}{trailing_slash}')
            if prune:
                i.rename(i.parent / new_filename)

    if verbose:
        # ○ ◎ ● ⊕ ☑ ☒ □ ■ ⌫ ⌈
        print('☒ [Remaining]')
        for item in tree_dict_iterator(path_list_to_tree_dict(pending_list['normal'])):
            print(item)

    click.echo('\n--- Statistics ---')
    click.echo(f'    Dir Total: {statistics["dir-total-count"]}')
    click.echo(f'   File Total: {statistics["file-total-count"]}')
    click.echo(f'Files Removed: {statistics["removed"]}')
    click.echo(f'Files Renamed: {statistics["renamed"]}')


if __name__ == '__main__':
    main()
