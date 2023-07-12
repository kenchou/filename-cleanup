# filename-cleanup
批量清除文件名中不想要的字词

根据设定的正则表达式清理文件名中不想要的部分。

使用方法

```
Usage: cleanup.py [OPTIONS] [TARGET_PATH]

Options:
  -c, --config <PATTERNS-CONFIG-FILE>
                                  yml config of cleanup patterns. Default:
                                  search ".cleanup-patterns.yml" in [TARGET-
                                  PATH, **TARGET-PATH.PARENTS, $HOME, BIN-
                                  PATH]
  -d, --remove / -D, --no-remove  Remove (or not) files and directories which
                                  matched remove patterns.  [default: remove]
  -r, --rename / -R, --no-rename  Rename (or not) files and directories which
                                  matched patterns.  [default: rename]
  -e, --remove-empty-dir / -E, --no-remove-empty-dir
                                  Remove (or not) empty dir.  [default:
                                  remove-empty-dir]
  -h, --enable-hash-match / -H, --disable-hash-match
                                  remove file if hash matched.  [default:
                                  disable-hash-match]
  -t, --skip-tmp-in-parents / -T, --no-skip-tmp-in-parents
                                  ignored if any parents dir is .tmp
                                  [default: no-skip-tmp-in-parents]
  --prune                         Execute remove and rename files and
                                  directories which matched clean patterns
  -v, --verbose                   -v=info, -vv=debug
  --help                          Show this message and exit.
```

清理规则文件 .cleanup-patterns.yml, 每行一条正则表达式。
规则文件查找路径：
1. 目标目录
2. 目标的目录的上级（向上一直追溯到根目录，直到找到第一个）
3. HOME 目录
4. 脚本所在目录

规则文件样例：

```yaml
remove: |-
  通配符
  /正则表达式
remove_hash: |-
  文件md5sum
cleanup: |-
  不想要的字样
  粗鄙的词汇
  正则表达式
```
