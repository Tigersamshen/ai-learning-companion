#!/bin/zsh
set -u
package_dir="${0:A:h}"
cd "$package_dir" || exit 1
python_bin="$(command -v python3 || true)"
if [[ -z "$python_bin" ]]; then
  for candidate in "$HOME"/.cache/codex-runtimes/*/dependencies/python/bin/python3(N) /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [[ -x "$candidate" ]]; then python_bin="$candidate"; break; fi
  done
fi
if [[ -z "$python_bin" ]]; then
  print '未找到 Python；请先安装 Python 3.10+，然后重新运行安装包。'
  exit 1
fi
"$python_bin" "$package_dir/setup.py" --install
result=$?
if [[ $result -eq 0 ]]; then
  print '\n插件安装完成。请按 README 在 Obsidian 中打开返回的学习笔记库，再运行 python3 setup.py --register-vault。'
else
  print '\n安装未完成，请查看上面的 JSON 错误和 README；已有学习数据会保留。'
fi
exit $result
