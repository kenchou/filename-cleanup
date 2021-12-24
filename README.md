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
                                  matched remove patterns. Default: --remove

  -r, --rename / -R, --no-rename  Rename (or not) files and directories which
                                  matched patterns. Default: --rename

  -e, --empty / -E, --no-empty    Remove (or not) empty dir. Default: --empty
  --prune                         Execute remove and rename files and
                                  directories which matched clean patterns

  -v, --verbose                   -v=info, -vv=debug
  --help                          Show this message and exit.
```

清理规则文件 .cleanup-patterns.yml, 每行一条正则表达式。
规则文件查找路径：
1. 目标目录
2. 目标的目录的上级（向上一直追溯到根目录，直到找到第一个）
2. HOME 目录
3. 脚本所在目录

规则文件样例：

```yaml
cleanup:
  不想要的字样
  粗鄙的词汇
  ^[-@]+
```

注: 配置文件 `.cleanup-patterns.yml` 和 [aria2rpc-oversee](https://github.com/kenchou/aria2rpc-oversee) 项目共用。本项目只用到 `cleanup` 段配置。
