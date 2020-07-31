#!/usr/bin/env python

import click
import re
import yaml

from fnmatch import fnmatch
from pathlib import Path
from typing import Pattern


global_options = {}
statistics = {'removed': 0, 'renamed': 0, 'dir-total-count': 0, 'file-total-count': 0}
patterns = {
    'remove': [],
    'cleanup': [],
}
pending_list = {
    'remove': [],
    'cleanup': [],
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


def recursive_scan(target_path):
    enabled_remove = global_options['feature_remove']
    enabled_rename = global_options['feature_rename']

    p = Path(target_path)
    nodes = sorted(p.glob('*'), key=lambda f: (0 if f.is_dir() else 1, f.name))     # 目录优先，深度优先
    for i in nodes:
        if enabled_remove:
            matched, pat = match_remove_pattern(i.name)
            if matched:
                if i.is_dir():  # remove dir and all children
                    children = [(x, None) for x in i.glob('**/*')]
                    pending_list['remove'].extend(children)
                    statistics['removed'] += len(children)
                    statistics['dir-total-count'] += len([1 for x, _ in children if x.is_dir()]) + 1
                    statistics['file-total-count'] += len([1 for x, _ in children if not x.is_dir()])
                else:
                    statistics['file-total-count'] += 1
                pending_list['remove'].append((i, pat))
                statistics['removed'] += 1
                continue

        if i.is_dir():
            recursive_scan(i)   # 递归遍历子目录, 深度优先
            statistics['dir-total-count'] += 1
        else:
            statistics['file-total-count'] += 1

        if enabled_rename:
            new_filename = clean_filename(i.name)
            if new_filename != i.name:
                statistics['renamed'] += 1
                pending_list['cleanup'].append((i, new_filename))


def get_badge(i):
    if i.is_dir():
        return 'cyan', '/'
    else:
        return 'green', ''


@click.command()
@click.argument('target-path', default='.')
@click.option('-c', '--config', 'cleanup_patterns_file', metavar='<PATTERNS-CONFIG-FILE>',
              help='file of cleanup patterns. Default: search "cleanup-patterns.yml" in [TARGET-PATH, $HOME, BIN-PATH]')
@click.option('-d/-D', '--rm/--no-rm', 'feature_remove', default=True,
              help='Remove (or not) files and directories which matched remove patterns')
@click.option('-r/-R', '--rename/--no-rename', 'feature_rename', default=True,
              help='Rename (or not) files and directories which matched patterns')
@click.option('--prune', is_flag=True, default=False,
              help='Execute remove and rename files and directories which matched clean patterns')
@click.option('-v', '--verbose', count=True)
def main(target_path, cleanup_patterns_file, feature_remove, feature_rename, prune, verbose):
    global_options['feature_remove'] = feature_remove
    global_options['feature_rename'] = feature_rename
    global_options['prune'] = prune

    # load config
    if not cleanup_patterns_file:
        guess_paths = [
            Path(target_path),
            Path.home(),
            Path(__file__).resolve().parent,  # ${BIN_PATH}/.aria2/
        ]
        cleanup_patterns_file = guess_path('cleanup-patterns.yml', guess_paths)
    if cleanup_patterns_file:
        load_patterns(cleanup_patterns_file)

    # scan dir
    recursive_scan(target_path)

    # cleanup
    if pending_list['remove'] or pending_list['cleanup']:
        click.echo("--- Summary ---")

    # remove
    if feature_remove:
        for i, pat in pending_list['remove']:
            _, trailing_slash = get_badge(i)
            extra_info = f' <= {pat}' if verbose and pat else ''
            color = 'red' if pat else None
            click.secho(f'[-] {i}{trailing_slash}{extra_info}', fg=color)
            if prune:
                i.rmdir() if i.is_dir() else i.unlink()

    # rename
    if feature_rename:
        for i, new_filename in pending_list['cleanup']:
            color, trailing_slash = get_badge(i)
            click.secho(f'[*] {i.parent}/{{ {i.name} => {new_filename} }}{trailing_slash}', fg=color)
            if prune:
                i.rename(i.parent / new_filename)

    click.echo('--- Statistics ---')
    click.echo(f'    Dir Total: {statistics["dir-total-count"]}')
    click.echo(f'   File Total: {statistics["file-total-count"]}')
    click.echo(f'Files Removed: {statistics["removed"]}')
    click.echo(f'Files Renamed: {statistics["renamed"]}')


if __name__ == '__main__':
    main()
