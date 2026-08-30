# PIPELINE-V2-OWNER-021

owner 数据流契约已补充：M1/N2 只保存 Chunk 内局部 mention；M3 验收后由服务端物化版本化 `OwnerBinding`，并派生 Chunk→人物和人物→观察/Chunk 两个访问方向。Chunk metadata 中的 `stable_owner_ids` 只是可重建多值缓存，不参与 Chunk hash，也不是身份事实源。N6 可从 Chunk 方向发现受影响人物，但 M4 的模型输入固定为单一稳定人物的观察批次。当前只完成设计澄清，运行时、持久化和索引尚未实现。
