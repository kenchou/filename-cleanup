# filename-cleanup
批量清除文件名中不想要的字词

根据设定的正则表达式清理文件名中不想要的部分。

使用方法

```bash
# 使用帮助
cleanup --help

# 扫描目标目录，列出哪些将做改动
cleanup [TARGET-PATH]

# 执行清理（改名）操作
cleanup [TARGET-PATH] --prune
```

清理规则文件 cleanup-patterns.txt, 每行一条正则表达式。
规则文件查找路径：
1. 目标目录
2. HOME 目录
3. 脚本所在目录

规则文件样例：

```
不想要的字样
粗鄙的词汇
^[-@]+
```