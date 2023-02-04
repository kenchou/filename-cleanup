#!/usr/bin/env python
import click
import hashlib
import logging
import re
import yaml

from collections import OrderedDict
from collections.abc import Mapping
from fnmatch import fnmatch
from pathlib import Path
from typing import Pattern, Optional


logging.basicConfig()
logger = logging.getLogger("cleanup")
LOG_LEVEL = {
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}
GLYPH_SPACE = "    "
GLYPH_BRANCH = "│   "
GLYPH_TEE = "├── "
GLYPH_LAST = "└── "

global_options = {}
patterns = {
    "remove": [],
    "remove_hash": [],
    "cleanup": [],
}
pending_list = {
    "remove": [],
    "cleanup": [],
    "normal": [],
}
statistics = {"removed": 0, "renamed": 0, "dir-total-count": 0, "file-total-count": 0}


def uniq_list_keep_order(seq):
    """get an uniq list and keep the elements order"""
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


def load_patterns(filename):
    with open(filename, encoding="utf8") as f:
        config = yaml.safe_load(f)
    for line in config.get("remove", "").splitlines():
        patterns["remove"].append(
            re.compile(line[1:], flags=re.IGNORECASE) if line.startswith("/") else line
        )
    for line in config.get("remove_hash", "").splitlines():
        patterns["remove_hash"].append(line)
    for line in config.get("cleanup", "").splitlines():
        patterns["cleanup"].append(re.compile(line, flags=re.IGNORECASE))


def match_remove_pattern(filename):
    for p in patterns["remove"]:
        if isinstance(p, Pattern):
            matched = p.search(str(filename))
            pat = p.pattern
        else:
            matched = fnmatch(filename, p)
            pat = p
        if matched:
            return matched, pat
    return False, None


def match_remove_hash(target_file: Path) -> tuple[bool, Optional[str]]:
    # match hash
    with target_file.open("rb") as f:
        md5sum = hashlib.md5(f.read()).hexdigest()
        if md5sum in patterns["remove_hash"]:
            return True, md5sum
    return False, None


def clean_filename(filename):
    for p in patterns["cleanup"]:
        filename = p.sub("", filename)
    return filename


def recursive_cleanup(target_path):
    enabled_remove = global_options["feature_remove"]
    enabled_rename = global_options["feature_rename"]
    enabled_remove_empty_dirs = global_options["feature_remove_empty_dirs"]
    skip_parent_tmp = global_options["skip_parent_tmp"]

    t = Path(target_path)
    is_dir = t.is_dir() and not t.is_symlink()  # do not follow symlinks, linux vs macOS
    # skip .tmp in sub-dirs
    if is_dir and ".tmp" == str(t.name):
        return
    # skip .tmp in parents dir
    if skip_parent_tmp and ".tmp" in t.parts:
        return

    if enabled_remove or enabled_remove_empty_dirs:
        children = (
            [(x, "Pruning branches") for x in reversed(list(t.glob("**/*")))] if is_dir else []
        )
        if enabled_remove:
            matched, pat = match_remove_pattern(t.name)
            # try match hash if file size <= 20Mb
            if not matched and t.is_file() and t.stat().st_size <= 20_000_000:
                matched, pat = match_remove_hash(t)
            if matched:
                if is_dir:  # remove dir and all children
                    pending_list["remove"].extend(children)
                    statistics["removed"] += len(children)
                    statistics["dir-total-count"] += (
                        len([1 for x, _ in children if x.is_dir()]) + 1
                    )
                    statistics["file-total-count"] += len(
                        [1 for x, _ in children if not x.is_dir()]
                    )
                else:
                    statistics["file-total-count"] += 1
                pending_list["remove"].append((t, pat))
                statistics["removed"] += 1
                return  # return early

        # empty dirs
        if enabled_remove_empty_dirs:
            if is_dir and not any([x for x, _ in children if x.is_file()]):
                pending_list["remove"].extend(children)
                pending_list["remove"].append((t, "Remove empty dirs"))
                statistics["removed"] += len(children) + 1
                statistics["dir-total-count"] += len([1 for x, _ in children if x.is_dir()]) + 1
                return  # return early

    if is_dir:
        nodes = sorted(t.iterdir(), key=lambda f: (0 if f.is_dir() else 1, f.name))  # 目录优先/深度优先
        for item in nodes:
            recursive_cleanup(item)  # 递归遍历子目录, 深度优先
        statistics["dir-total-count"] += 1
    else:
        statistics["file-total-count"] += 1

    if enabled_rename:
        new_filename = clean_filename(t.name)
        if new_filename != t.name:
            statistics["renamed"] += 1
            pending_list["cleanup"].append((t, new_filename))
            return  # return early
    # remaining dirs/files
    pending_list["normal"].append(t)


def get_badge(i):
    if i.is_dir():
        return "cyan", "/"
    else:
        return "green", ""


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


def tree_dict_iterator(dir_path, prefix=""):
    """A recursive generator, given a directory Path object
    will yield a visual tree structure line by line
    with each line prefixed by the same characters
    """
    contents = dir_path.keys()
    # contents each get pointers that are ├── with a final └── :
    pointers = [GLYPH_TEE] * (len(contents) - 1) + [GLYPH_LAST]
    for pointer, path in zip(pointers, contents):
        node = dir_path[path]
        if isinstance(node, str):  # append symlink
            path = f"{path}@ -> {node}"
        yield f"{prefix}{pointer}{path}"
        if isinstance(node, Mapping):  # extend the prefix and recurse:
            extension = GLYPH_BRANCH if pointer == GLYPH_TEE else GLYPH_SPACE
            # i.e. space because last, └── , above so no more |
            yield from tree_dict_iterator(node, prefix=f"{prefix}{extension}")


@click.command()
@click.argument("target-path", type=click.Path(exists=True), default=".")
@click.option(
    "-c",
    "--config",
    "cleanup_patterns_file",
    metavar="<PATTERNS-CONFIG-FILE>",
    help="yml config of cleanup patterns. "
    'Default: search ".cleanup-patterns.yml" in [TARGET-PATH, **TARGET-PATH.PARENTS, $HOME, BIN-PATH]',
)
@click.option(
    "-d/-D",
    "--remove/--no-remove",
    "feature_remove",
    default=True,
    help="Remove (or not) files and directories which matched remove patterns. Default: --remove",
)
@click.option(
    "-r/-R",
    "--rename/--no-rename",
    "feature_rename",
    default=True,
    help="Rename (or not) files and directories which matched patterns. Default: --rename",
)
@click.option(
    "-e/-E",
    "--empty/--no-empty",
    "feature_remove_empty_dirs",
    default=True,
    help="Remove (or not) empty dir. Default: --empty",
)
@click.option(
    "-t/-T",
    "--skip-tmp-in-parents/--no-skip-tmp-in-parents",
    "skip_parent_tmp",
    default=False,
    help="ignored if any parents dir is .tmp",
)
@click.option(
    "--prune",
    is_flag=True,
    default=False,
    help="Execute remove and rename files and directories which matched clean patterns",
)
@click.option("-v", "--verbose", count=True, help="-v=info, -vv=debug")
def main(
    target_path,
    cleanup_patterns_file,
    feature_remove,
    feature_rename,
    feature_remove_empty_dirs,
    skip_parent_tmp,
    prune,
    verbose,
):
    logger.setLevel(LOG_LEVEL[min(verbose, max(LOG_LEVEL))])

    global_options["feature_remove"] = feature_remove
    global_options["feature_rename"] = feature_rename
    global_options["feature_remove_empty_dirs"] = feature_remove_empty_dirs
    global_options["skip_parent_tmp"] = skip_parent_tmp
    global_options["prune"] = prune

    target = Path(target_path)

    # guess the config location
    if not cleanup_patterns_file:
        guess_paths = (
            [target]
            + list(target.absolute().parents)
            + [
                Path.home(),
                Path(__file__).resolve().parent,  # ${BIN_PATH}
            ]
        )
        cleanup_patterns_file = guess_path(".cleanup-patterns.yml", guess_paths)

    # load patterns from config
    if cleanup_patterns_file:
        logger.info(f"{cleanup_patterns_file=}")
        load_patterns(cleanup_patterns_file)

    # recursive scan the target dir
    recursive_cleanup(target)

    # cleanup
    if pending_list["remove"] or pending_list["cleanup"]:
        click.echo("\n--- Summary ---")

    # remove junk files
    if feature_remove:
        for i, pat in pending_list["remove"]:
            click.secho("[-] ", fg="red", nl=False)

            color, trailing_slash = get_badge(i)
            if not pat:
                color = None
            click.echo(f"{i.parent}/", nl=False)
            click.secho(f"{i.name}{trailing_slash}", fg=color, nl=False)
            click.echo(f" <= {pat}" if verbose >= 3 and pat else "")
            if prune:
                # do not follow symlink
                i.rmdir() if i.is_dir() and not i.is_symlink() else i.unlink()

    # clean/rename filename
    if feature_rename:
        for i, new_filename in pending_list["cleanup"]:
            click.secho("[*] ", fg="yellow", nl=False)

            color, trailing_slash = get_badge(i)
            old = click.style(i.name, fg=color)
            new = click.style(new_filename, fg="yellow")
            click.echo(f'{i.parent}/{{ "{old}" => "{new}" }}{trailing_slash}')
            if prune:
                i.rename(i.parent / new_filename)

    if verbose:
        # ○ ◎ ● ⊕ ☑ ☒ □ ■ ⌫ ⌈
        print("☒ [Remaining]")
        for item in tree_dict_iterator(path_list_to_tree_dict(pending_list["normal"])):
            print(item)

    click.echo("\n--- Statistics ---")
    click.echo(f'    Dir Total: {statistics["dir-total-count"]}')
    click.echo(f'   File Total: {statistics["file-total-count"]}')
    click.echo(f'Files Removed: {statistics["removed"]}')
    click.echo(f'Files Renamed: {statistics["renamed"]}')


if __name__ == "__main__":
    main()
