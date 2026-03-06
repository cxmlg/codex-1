# UE5 Blueprint API Scanner

用于扫描 UE5 C++ 代码中可被蓝图使用的符号，并导出清单。

## 支持的类型

- `UCLASS(...)`：包含 `Blueprintable` / `BlueprintType`
- `UINTERFACE(...)`：包含 `Blueprintable` / `BlueprintType`
- `USTRUCT(...)`：包含 `BlueprintType`
- `UENUM(...)`：包含 `BlueprintType`
- `UPROPERTY(...)`：包含 `BlueprintReadOnly` / `BlueprintReadWrite` / `BlueprintGetter` / `BlueprintSetter`
- `UFUNCTION(...)`：包含 `BlueprintCallable` / `BlueprintPure` / `BlueprintImplementableEvent` / `BlueprintNativeEvent`

> 说明：脚本支持单行和多行宏参数（例如带 `meta=(...)` 的写法）。

## 用法

```bash
python3 scripts/list_blueprint_api.py /path/to/YourUEProject --md blueprint_api.md --json blueprint_api.json
```

- 不传 `--md`/`--json` 时：输出 Markdown 到终端。
- 传 `--md`：写入 Markdown 报告。
- 传 `--json`：写入 JSON 报告。

## 进度与统计

- 默认会在 stderr 打印每个文件的扫描进度（`[scan i/n] ...`）。
- 默认会在扫描结束后打印统计（文件总数、失败数、各类型命中数量）。
- 可通过以下参数关闭：

```bash
python3 scripts/list_blueprint_api.py /path/to/YourUEProject --no-progress --no-stats
```
