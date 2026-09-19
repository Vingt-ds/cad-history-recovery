# gate6-precheck-0.1：Oracle operationalization contract

状态：设计原则已获批准；本文件允许独立实现及qualification准备，正式12-run oracle campaign尚未获准。不是benchmark、推断实现或历史恢复结果。机器参数见`config/gate6_precheck_v0_1.json`；本文与参数共同构成合同，冲突即binding failure。

## 1. metadata / provenance

基线tag为`gate0-4-frozen-baseline-v1`，完整commit为`c3e448525e9424383e847332f4d0afc1444e7380`。分支`gate6-operation-precheck`直接起于该commit。问题定义来自`ca90c888a4d41649523c32c33de4139acc585411`，原blob为`b7abbc8fa82ff252e1c563d2626cfdfee7e2e72a`，原文原样迁移。

运行前绑定完整`specification_commit`、合同blob、参数blob、合同SHA-256、`implementation_commit`及implementation tree。SHA从Git/字节计算，不预造自引用值。实现commit须包含相同specification文件字节；工作树必须干净。缺失绑定、字节不一致或执行未获准时禁止创建正式campaign。

`authoritative_comparison_artifact = exported_and_reimported_STEP`。所有tool identity、解析验证、观测提取、图比较、几何等价和重复性判定由外部比较器对重新读入的STEP完成。Fusion内存诊断没有PASS权威。F3D是timeline审计资产，不是比较权威。

## 2. coordinate_system / units

固定右手世界坐标，原点(0,0,0)，轴为标准XYZ。长度mm、面积mm²、体积mm³。Fusion内部cm须显式转换。禁止对齐、平移、旋转、镜像、尺度归一化和best-fit registration。各棱柱用固定Z平面的矩形沿+Z正距离生成。

## 3. B specification

`B=[0,40]×[0,30]×[0,20]`，体积24000。profile在z=0，XY顶点依次(0,0),(40,0),(40,30),(0,30)，距离20。独立tool须有效、closed、单solid、单component、单shell，6平面face/12直线edge/8vertex。此计数只约束初始箱体，不约束布尔结果。

## 4. J specification

`J=[32,48]×[7,19]×[5,14]`，profile在z=5，沿+Z距离9。体积1728，与B重叠864，新增864。J保持为不可变工具；每次run独立生成、落盘、重新读取核验。不同run不得复用Fusion body。

三边互异的B仍有对称性。枚举绕B中心对XYZ各坐标取正/负的8个变换；除恒等变换外，没有变换保持带标签的J/C规格。不得用自动配准消除绝对位置。

## 5. C specification

OS：`C=[36,44]×[11,16]×[8,12]`，z=8、距离4，体积160；C包含于J，与B交80。

DE：`C=[8,14]×[21,26]×[3,10]`，z=3、距离7，体积210；C严格位于B内。`dist(J,C)=sqrt(328)`mm。两组均使用参数文件中相同B/J。允许内部空腔。

## 6. target/tool role semantics

`S0=B`。Join为`reg_union(S_current,J)`，Cut为`reg_difference(S_current,C)`。Target始终是上一构造状态唯一结果solid；固定的是角色，不是跨步骤对象身份。显式对象引用选target/tool，禁止默认selection/participant。需要消耗工具时使用已核验的副本，原tool保持不变。禁止through_all、to-object和前序face/edge引用。

每步结果要求有效closed solid，`solid_count=1`且`connected_component_count=1`。保留的工具不计入结果，且不得混入结果STEP。一个solid可有多个shell。

## 7. analytic expected geometry

独立解析oracle只用坐标区间、交集和有理数运算，不调用CAD布尔生成预期。

|量/mm³|OS|DE|
|---|---:|---:|
|B|24000|24000|
|J|1728|1728|
|C|160|210|
|after J|24864|24864|
|after C|23920|23790|
|final JC|24704|24654|
|final CJ|24864|24654|
|order symmetric difference|160|0|

`V(B∪J)=V(B)+V(J\B)`；`V(B\C)=V(B)-V(C∩B)`；JC最终减去`V(C∩(B∪J))`；CJ最终加上`V(J\(B\C))`。按regularized实体内部/体积意义，JC包含于CJ，差异为J∩C，不比较零测度边界归属。

每run比较工具、第一步及最终体积和完整解析目标；跨顺序比较实际对称差与解析差异。另独立检查shell数量：OS after_J/after_C/final_CJ为1、final_JC为2；DE after_J为1、after_C及两个final为2。不预设布尔结果face/edge数量。

## 8. operation-effect contract

各字段必须有`expected_mm3/measured_mm3/threshold_mm3/analytic_agreement/pass`。实测effect >0.01mm³且与解析误差≤0.001mm³。

|字段|定义|OS|DE|
|---|---|---:|---:|
|operation_effect.join_on_base|V(J\B)|864|864|
|operation_effect.cut_after_join|V(C∩(B∪J))|160|210|
|operation_effect.cut_on_base|V(C∩B)|80|210|
|operation_effect.join_after_cut|V(J\(B\C))|944|864|

各run记录实际执行的两项，group覆盖四项每次重复；任何false使group失败。

## 9. connectivity contract

独立字段`connectivity.join_on_base`为V(J∩B)，两组864；`connectivity.join_after_cut`为V(J∩(B\C))，OS784、DE864。均要求>0.01mm³及解析误差≤0.001mm³。另检查每步有效单连通solid，不以重叠体积代替连通性。

## 10. order-sensitive candidate

OS解析差异160mm³，必须在执行前满足设计分离阈值10mm³。9个跨顺序配对均要求实测对称差≥10mm³、与160差≤0.001mm³、固定双向表面指标≥0.1mm及完整观测为different。失败读取不能充当different。组通过后才称order-sensitive control。

## 11. disjoint-equivalence candidate

DE最短距离必须>1mm且与sqrt(328)误差≤0.00001mm。6个终态全部15个配对同时满足几何和图观测等价。几何相同但face split不同不得通过。通过后才称observationally equivalent control。

## 12. gauge normalization

仅允许轴对齐plane及line；circle/cylinder/spline等返回unsupported_observable_type，不设计通用曲面回退。平面用单位n及n·x=d，首个绝对值>1e-12分量为正；与世界轴夹角≤1e-8rad。line方向同样规范，位置为距原点最近点，边界用实际端点。面物理外向方向独立于底层参数法向。

投影固定：±X→YZ，±Y→XZ，±Z→XY；基底叉积符号h=(+1,-1,+1)。物理外向符号s下outer wire有向面积符号为h*s，inner相反。规范遍历消除底层参数翻转；保留EdgeUse次序及方向，忽略循环起点。不合并face/edge，不改拓扑。

坐标仅将绝对相等值去重；不同坐标间距≤1e-5mm、导致无法唯一确定cell边界时返回comparison_indeterminate，不进行顺序相关聚类/吸附。不同拓扑vertex即使坐标相同也保持不同节点。

## 13. B-rep observable schema

图节点：Solid/Shell/Face/Wire/EdgeUse/Edge/Vertex。关系：contains、Wire的EdgeUse next、EdgeUse references Edge、Edge connects Vertex；保留方向与多重性。属性：Solid体积/质心/包围盒；Shell闭合与outer/cavity；Face规范平面/物理外向/面积/质心；Wire outer/inner；EdgeUse规范遍历方向；Edge规范直线/长度/端点；Vertex世界坐标。

STEP使用冻结OCP reader transfer默认策略，记录相关Interface_Static读取参数。禁止可选heal、sew、clean、same-domain unify以及比较前重新导出；reader固有转换属于观测链。拓扑直接来自该shape，临时布尔测量shape不可替代它。

Wire角色：按EdgeUse顺序构成闭合轴对齐简单polygon；闭合误差≤1e-5mm。距任一线段≤1e-5判BOUNDARY，否则使用半开区间偶奇射线法。拒绝自交、不同loop相交或接触；唯一depth0为outer，depth1为inner，更深嵌套失败。包含判定使用一个loop的边界点对其他不相交loop测试，不使用可能落进孔内的polygon质心。

Face内部点：所有wire vertex投影坐标划分cell，中心通过outer内且全部hole外判定；按面积降序、坐标字典序选首cell中心。点必须距边界>1e-5mm。沿规范轴法向±0.001mm对完整solid分类，classifier tolerance=1e-7mm；恰好一侧IN另一侧OUT，OUT侧为物理外向。ON/UNKNOWN/同侧结果均indeterminate，不调probe。

Shell角色：先验证shell闭合且连通、不同shell不相交。对每对shell，以前者字典序首个vertex对后者独立闭合边界做包含判断，不能对整个材料solid分类替代。使用+X射线与后者矩形face cells相交的奇偶性；射线落在矩形边界或共面时indeterminate，不换方向。唯一depth0为outer，其余须depth1 cavity；无唯一外壳或更深嵌套失败。包围盒仅快速排除，不证明包含。

## 14. graph equivalence

完整带属性有向多重图同构；类型、关系、离散属性精确匹配，数值按合同容差。存在一个合法双射即等价，多映射允许。计数/指纹只能fast-reject/index；碰撞记录后仍做完整比较。上限10000节点、1000000搜索状态，超限或无法规范化返回comparison_indeterminate，不回退geometry-only。

## 15. geometry equivalence

等价要求体积差及对称差≤0.001mm³、固定双向表面指标≤0.0001mm、有效实体及component数相等。参数长度/位置/质心/bbox容差0.00001mm，角度1e-8rad，面积0.001mm²。布尔测量无效或异常不得当零。

Tolerance rationale：这些是预选工程验收界限与刻意尺度分离，不是拟合工业精度。最小effect80比0.01为8000倍；OS160比0.001为160000倍、比10分离阈值为16倍；DE sqrt(328)>18mm，比1mm间隙阈值大18倍；surface separation0.1比surface equivalence1e-4为1000倍。0.001mm normal probe大于参数容差100倍，并远小于设计中最小mm级特征尺度。阈值不根据oracle结果调整。

## 16. surface sampling contract

名称deterministic_bidirectional_sampled_max_surface_distance，非精确Hausdorff。按第12节投影，将face所有wire vertex坐标划分矩形cell，按第13节polygon规则决定中心inside/outside。每个有效cell以64×64等间距cell-center采样；另加每edge两端点/中点；精确坐标去重后XYZ排序。seed=null，无随机。所有外表面与空腔表面均覆盖。

点到目标边界距离取所有目标矩形的解析欧氏最短距离；两方向所有点距离最大值再取max。失败分解/空点集为indeterminate，禁止换p95。解析目标使用区间占据网格生成外露矩形，不用CAD布尔。采样密度可因face split变化，故只声明固定采样指标。

## 17. repeatability contract

每round重新启动Fusion进程，4个fresh documents。记录PID、进程启动时间、Fusion/Python/OS及依赖版本、插件清单、脚本commit、round时间。三round进程启动身份须不同。

环境精确值见参数：Fusion2704.1.53/Fusion Python3.14.0/external Python3.11.16/CadQuery2.8.0/OCP7.9.3.1/NumPy2.4.6/SciPy1.17.1/Windows-10-10.0.22621-SP0。此为要求，不是本机实时状态声明。不匹配则preflight失败。

同case的3个终态及3个第一步分别两两比较，体积0.001mm³、surface0.0001mm和完整graph等价。不要求跨run文件hash相同。

## 18. 12-run execution matrix

|round|1|2|3|4|
|---|---|---|---|---|
|R1|OS_JC_R1|DE_CJ_R1|OS_CJ_R1|DE_JC_R1|
|R2|DE_JC_R2|OS_CJ_R2|DE_CJ_R2|OS_JC_R2|
|R3|OS_CJ_R3|DE_JC_R3|OS_JC_R3|DE_CJ_R3|

固定交错，无随机；3轮不声称实现4位置完全平衡。不得调换、覆盖或以补跑替代失败。

## 19. evidence package schema

正式root为`runs/gate6/precheck/gate6-precheck-0.1/<specification_commit>/<campaign_uuid>/`，排他创建、不可覆盖。未获执行批准不得建立该root。

每run：run_manifest/specifications/environment/tool_identity/operation_effect/connectivity/analytic_comparison/execution_log/final_status/artifact_hashes JSON，及artifacts下base.step、join_tool.step、cut_tool.step、after_modifier_1.step、final.step、construction.f3d。全部5个STEP重新读入后裁决。run记录完整绑定、group/order/round/position/UUID。campaign包含execution_matrix、comparisons、group_results、precheck_result及SHA256SUMS。

spec哈希按RFC8785 canonical JSON；JSON UTF-8，禁止NaN/Infinity。geometry fingerprint仅索引，tool identity必须完整比较；文件SHA用于完整性。封存后不改run，汇总另建。失败保留产物。

## 20. failure taxonomy

代码及stage精确映射见参数failure_stages。每个failure含code、stage、message、evidence_paths、primary boolean。第一个使run无法继续的合同失败为primary，后续只读检查为secondary diagnostics。tool_identity_failure、comparison_indeterminate不得混为replay_failure。

执行中断、binding、环境、tool identity、执行、解析、观测提取、比较、重复性和证据完整性分别报告。任何不确定比较均不能通过。

## 21. group-level PASS logic

OS：6run全部有效，所有身份/effect/connectivity/解析/同序重复性通过，9跨序对均满足完整分离合同，证据完整。

DE：6run全部有效，身份/effect/connectivity/解析/间隙通过，6终态全部15对完整观测等价，中间状态同序重复性通过，证据完整。共同B/J跨group一致，同group B/J/C跨order和round一致。

## 22. precheck-level PASS logic and implementation qualification

PASS=OS通过 AND DE通过 AND恰好12个要求run AND矩阵/来源/完整性通过。状态NOT_STARTED/RUNNING/PASS/FAIL/ABORTED。确定性合同失败立即停止新oracle运行；中断为ABORTED。失败后只读诊断允许。

正式campaign前必须通过implementation qualification。测试放`tests/gate6_precheck/`，独立synthetic规格放`testdata/gate6_precheck_qualification/`；临时产物仅系统临时目录或qualification专用目录。不得使用正式run ID/root，不计为precheck evidence。

资格测试覆盖spec hash、解析量、独立小型synthetic STEP roundtrip、gauge、XZ方向符号、wire孔/坏loop、shell空腔、graph ID置换/face split、固定采样、probe失败、完整性封存和failure stage。禁止把OS/DE完整双序列正式几何作为qualification暗跑。静态解析重算正式参数允许。

资格通过后冻结implementation commit，执行不生成正式证据的provenance/environment/preflight，提交pre-execution报告待批准。资格通过不等于Fusion真实session执行已经通过。

## 23. oracle/inference firewall

B/J/C、顺序/标签、解析预期、中间体和目录只属oracle。未来推断仅接收final history-free B-rep和声明观测；不得读取oracle参数、路径语义或日志。比较器能读oracle不赋予推断同权。已知预检案例不能重新命名为held-out。未冻结未来搜索域/benchmark规模。

## 24. version-bump rules

首run后尺寸、操作、角色、容差、观测/gauge、图/采样、环境、矩阵或执行/比较语义变化均使本冻结失效：保存v0.1 FAIL/ABORTED，新v0.2、新批准specification commit、新implementation commit、新root，重做全12run。不得跨版本拼接或追认。纯说明补充单独存放，不改已绑定合同。
