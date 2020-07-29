#!/usr/bin/env python

import click
import re

from pathlib import Path


statistics = {'D': 0, '-': 0, 'dir-total-count': 0, 'file-total-count': 0}
clean_patterns = []
clean_list = []


def uniq_list_keep_order(seq):
    """get a uniq list and keep the elements order"""
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]


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
        for line in f.read().splitlines():
            clean_patterns.append(re.compile(line, flags=re.IGNORECASE))
    pass


def clean_filename(filename):
    for p in clean_patterns:
        filename = p.sub('', filename)
    return filename


def recursive_scan(target_path, prune=None, verbose=None):
    if verbose:
        print(f'{str(target_path)}/')
    p = Path(target_path)
    # print('## Current in', str(p))
    nodes = sorted(p.glob('*'), key=lambda f: (0 if f.is_dir() else 1, f.name))
    # print(nodes)
    for i in nodes:
        if i.is_dir():
            recursive_scan(i, prune)   # 递归遍历子目录
            color = 'cyan'
            trailing_slash = '/'
            statistics['dir-total-count'] += 1
            node_type = 'D'
        else:
            color = 'green'
            trailing_slash = ''
            statistics['file-total-count'] += 1
            node_type = '-'
        new_filename = clean_filename(i.name)
        if new_filename != i.name:
            statistics[node_type] += 1
            clean_list.append((i, new_filename))
            if verbose:
                click.secho(f'[*] {i.parent}/{{ {i.name} => {new_filename} }}{trailing_slash}', fg=color)
        else:
            if verbose:
                print(f'    {i.name}{trailing_slash}')


@click.command()
@click.argument('target-path', default='.')
@click.option('--prune', is_flag=True, default=False, help='rename files and directories which matched clean patterns')
@click.option('-c', '--cleanup-patterns-file',
              help='file of cleanup patterns. Default: search "cleanup-patterns.txt" in [TARGET-PATH, $HOME, BIN-PATH]')
@click.option('-v', '--verbose', count=True, help='Increase output verbosity.')
def main(target_path, prune, cleanup_patterns_file, verbose):
    if not cleanup_patterns_file:
        guess_paths = [
            Path(target_path),
            Path.home(),
            Path(__file__).resolve().parent,  # ${BIN_PATH}/.aria2/
        ]
        cleanup_patterns_file = guess_path('cleanup-patterns.txt', guess_paths)
    if cleanup_patterns_file:
        load_patterns(cleanup_patterns_file)
    recursive_scan(target_path, prune, verbose)

    if clean_list:
        click.echo("--- Summary ---")
    for i, new_filename in clean_list:
        if i.is_dir():
            color = 'cyan'
            trailing_slash = '/'
        else:
            color = 'green'
            trailing_slash = ''
        click.secho(f'[*] {i.parent}/{{ {i.name} => {new_filename} }}{trailing_slash}', fg=color)
        if prune:
            i.rename(i.parent / new_filename)

    click.echo('--- Statistics ---')
    click.echo(f'    Dir Total: {statistics["dir-total-count"]}')
    click.echo(f' Renamed Dirs: {statistics["D"]}')
    click.echo(f'   File Total: {statistics["file-total-count"]}')
    click.echo(f'Renamed Files: {statistics["-"]}')


if __name__ == '__main__':
    main()
