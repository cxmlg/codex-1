# UE5 Blueprint API Scanner

这个仓库提供了一个脚本，用于扫描 UE5 C++ 代码中可被蓝图使用的符号：

- `UCLASS(...)` 中包含 `Blueprintable` / `BlueprintType`
- `USTRUCT(...)` 中包含 `BlueprintType`
- `UPROPERTY(...)` 中包含 `BlueprintReadOnly` / `BlueprintReadWrite` / `BlueprintGetter` / `BlueprintSetter`
- `UFUNCTION(...)` 中包含 `BlueprintCallable` / `BlueprintPure` / `BlueprintImplementableEvent` / `BlueprintNativeEvent`

## 用法

```bash
python3 scripts/list_blueprint_api.py /path/to/YourUEProject --md blueprint_api.md --json blueprint_api.json
```

如果不传 `--md`/`--json`，会直接输出 Markdown 到终端。
