The evaluation of the LLM-based classification requires a reliable reference. This chapter describes how this reference was established for the investigated assemblies. The ground truth was developed through an iterative process in which initial labels based on the assembly designations and documentation were revised using the results of a labeling workshop and a subsequent review against the codebook. First, the assembly dataset and the codebook defining the functional classes are presented. The chapter then describes the design and evaluation of the workshop, during which human classifications and processing times were recorded. The chapter concludes with the implications of the results for the LLM experiments in Chapter 5, where a final review of the ground truth is also described.

评估基于大语言模型的分类需要可靠的参考依据。本章介绍如何为所研究的装配体建立这一参考依据。Ground Truth 通过迭代过程建立。首先根据装配体名称和文档确定初始标签，然后结合标注研讨会的结果以及随后依据分类手册进行的审核，对这些标签进行修订。本章首先介绍装配体数据集和定义功能类别的分类手册。随后介绍标注研讨会的设计与评估，研讨会中记录了人工分类结果和处理时间。最后，本章说明这些结果对第 5 章大语言模型实验的影响。第 5 章还将介绍对 Ground Truth 的最终审核。

## 4.1 Assembly Dataset

### ① 数据集概述

This study uses a dataset of 199 assemblies from the field of handling technology (Handhabungstechnik) at BMG. The dataset consists of two parts: a primary set of 129 assemblies and a supplementary set of 70 assemblies, both subject to the same documentation requirements. Both sets were classified in labeling workshops and provide a common test basis for the human classification reported in this chapter and the LLM experiments in Chapter 5, with the primary set used for the main experiments and the supplementary set for additional experiments. Using an identical basis ensures that human and model classifications can be compared directly.

本研究使用 BMG 操作技术领域的 199 个装配体组成的数据集。数据集包括两部分，分别是包含 129 个装配体的主数据集和包含 70 个装配体的补充数据集，两者遵循相同的文档资料要求。两部分均在标注研讨会中进行了分类，并为本章介绍的人工分类和第 5 章的大语言模型实验提供共同的测试基础。其中，主数据集用于主要实验，补充数据集用于补充实验。使用相同的数据基础，可以直接比较人工分类和模型分类的结果。

### ② 领域与研究范围

In line with the research project outlined in Section 1.1, the investigation focuses on handling technology, as handling assemblies constitute a central part of the special-purpose machinery developed at BMG. The assemblies were selected from the Teamcenter and DFC databases and came from BMG projects carried out over roughly the past five years at sites in several countries, including Germany, China and Turkey. The dataset comprises main assemblies and subassemblies designed and manufactured in-house by BMG; complete workstations and purchased components are not considered.

根据第 1.1 节介绍的研究项目，本研究聚焦于操作技术领域，因为操作类装配体是 BMG 开发的非标设备的核心组成部分。装配体选自 Teamcenter 和 DFC 数据库，来自过去约五年 BMG 在德国、中国和土耳其等多个国家的站点开展的项目。数据集包含由 BMG 自行设计和制造的主装配体与子装配体，不包括完整工位和外购件。

### ③ 选样标准与资料完整性

Assemblies were eligible for selection only if CAD data, a technical drawing and a structured bill of materials were available. In addition, data sheets of the actuators that determine the main function, such as drives, are available for the majority of assemblies. As a result, the amount of supplementary documentation varies from one assembly to another. This variation reflects the conditions under which assemblies are retrieved in engineering practice and was retained in the dataset. The supplementary set was compiled to improve the balance among classes in the overall dataset.

选入数据集的装配体必须具备 CAD 数据、技术图纸和结构化物料清单。此外，大多数装配体还具有决定其主要功能的执行器（如驱动装置）的数据表。因此，不同装配体的补充资料数量有所不同。这种差异反映了工程实践中检索装配体时的实际情况，因此在数据集中予以保留。补充数据集的收集旨在使整体数据集的类别分布更加均衡。

### ④ 数据来源

The technical information was retrieved from two systems. Teamcenter is the product lifecycle management system used to store engineering data, including CAD models and drawings. The Documentation Tool for Customers (DFC) links bills of materials and project structures from SAP and Autodesk Vault with the associated technical documentation [citation]. The system supports retrieval of drawings, 3D models and technical documents for machines, workstations and components using their identification numbers. Where documents were not available in DFC, technical drawings and bills of materials were generated directly from the engineering data in Teamcenter. For each assembly, the available material comprises the German and English designations, at least five CAD screenshots (one isometric view and four views taken from the corners of the assembly), technical drawings, bills of materials and data sheets.

技术信息来自两个系统。Teamcenter 是用于存储 CAD 模型和图纸等工程数据的产品生命周期管理系统。客户文档工具（DFC）将 SAP 和 Autodesk Vault 中的物料清单、项目结构与相应的技术文档关联起来 [citation]。该系统支持通过编号检索机器、工位和组件的图纸、三维模型及技术文档。对于 DFC 中无法获取的文档，技术图纸和物料清单直接根据 Teamcenter 中的工程数据生成。每个装配体的可用资料包括德文和英文名称、至少五张 CAD 截图（一张等轴测视图和四张从装配体各角度拍摄的视图）、技术图纸、物料清单和数据表。

### ⑤ 类别分布

Table 4.1 shows the distribution of assemblies across the seven classes defined in the codebook (Section 4.2). With between 22 and 31 assemblies per class, the dataset is approximately balanced.

表 4.1 展示了装配体在分类手册（第 4.2 节）定义的七个类别中的分布。每个类别包含 22 至 31 个装配体，数据集的类别分布总体较为均衡。

**Table 4.1: Distribution of assemblies by functional class / 表 4.1：各功能类别的装配体分布**

| Class / 类别 | Primary set / 主数据集 | Supplementary set / 补充数据集 | Total / 合计 |
| --- | ---: | ---: | ---: |
| Gripper / 夹爪 | 20 | 10 | 30 |
| Linear Unit / 直线单元 | 21 | 10 | 31 |
| Rotary Unit / 旋转单元 | 18 | 10 | 28 |
| Robot / 机器人 | 20 | 10 | 30 |
| Multi-Axis System (Gantry) / 多轴系统（龙门） | 17 | 5 | 22 |
| Combined Unit / 组合单元 | 24 | 5 | 29 |
| None of the Available Classes / 不属于任何可用类别 | 9 | 20 | 29 |
| **Total / 合计** | **129** | **70** | **199** |

### ⑥ 初始标签

Prior to the workshops, each of the 199 assemblies was assigned an initial class label based on its designation and documentation in Teamcenter and a manual preliminary review. These initial labels are provisional because assembly designations do not always indicate the functional class. Their revision is described in Sections 4.4 and 4.5.

在研讨会之前，根据每个装配体在 Teamcenter 中的名称和文档资料，并结合人工初步审核，为 199 个装配体分别分配了初始类别标签。由于装配体名称并不总能反映其功能类别，这些初始标签属于暂定标签。标签的修订过程见第 4.4 节和第 4.5 节。

## 4.2 Classification Scheme and Codebook | 分类体系与 Codebook

**① Codebook 的用途**

A codebook was developed to support consistent classification (Appendix A). It defines the classes, the criteria for assigning an assembly to a class and the procedure for borderline cases. Workshop participants and the LLM follow the same classification rules set out in the codebook.

为确保分类一致，本研究制定了分类手册（Codebook，见附录 A）。手册规定了各个类别、将装配体归入某一类别的判据，以及边界情况的处理流程。标注研讨会的参与者和大语言模型遵循手册中规定的同一套分类规则。

### 4.2.1 Classes | 类别

**② 类别概述**

Following the concept of main function introduced in Section 2.1, each assembly is assigned to exactly one class according to its dominant main function, that is, the purpose for which the assembly exists in the process. The classification scheme includes six categories for handling functions and one category for assemblies that fall outside those six (Figure 4.1, Table 4.2). Apart from the gripper, the handling classes are distinguished by the number of rotary (R) and translational (T) actuators that realise the motion sequence.

根据第 2.1 节介绍的主功能概念，每个装配体按其主导功能归入且仅归入一个类别。这里的主导功能是指装配体在工艺过程中所承担的主要作用。分类体系包含六个操作功能类别，以及一个用于归纳不属于这六类的装配体的类别（图 4.1、表 4.2）。除夹爪外，各操作功能类别根据实现运动过程所需的旋转执行器（R）和平移执行器（T）数量来区分。

**[Insert Figure 4.1 here / 在此插入图 4.1]**

*Figure 4.1. Illustrations of the seven classes / 图 4.1 七类装配体示意图*

**Table 4.2. Classes of the codebook / 表 4.2 Codebook 的类别**

| Class / 类别 | Criterion / 判据 | Main function / 主功能 |
| --- | --- | --- |
| Gripper / 夹爪 | R = 0, T = 0, gripping function | Gripping, holding, clamping, picking up or placing workpieces with direct contact / 通过直接接触工件进行抓取、保持、夹紧、拾取或放置 |
| Linear Unit / 直线单元 | R = 0, T = 1 | Transporting, moving or positioning a part, tool or further assembly along exactly one direction / 沿单一方向运输、移动或定位零件、工具或其他装配体 |
| Rotary Unit / 旋转单元 | R = 1, T = 0 | Rotating, swivelling, turning or aligning a part, tool or workpiece carrier about exactly one axis / 绕单一轴线旋转、摆动、翻转或对准零件、工具或工件载体 |
| Robot / 机器人 | R ≥ 2, T = 0 | Flexible handling, positioning or processing through freely programmable motion over at least two rotary joints / 通过至少两个旋转关节的可自由编程运动，实现柔性操作、定位或加工 |
| Multi-Axis System (Gantry) / 多轴系统（龙门） | R = 0, T ≥ 2, gantry test passed | Positioning, transporting or handling parts, tools or grippers in a freely addressable Cartesian workspace / 在可自由到达各位置的笛卡尔工作空间内定位、运输或操作零件、工具或夹爪 |
| Combined Unit / 组合单元 | T ≥ 1, R + T ≥ 2, no gantry | Picking up, transferring, turning, aligning or handing over workpieces in a task-specific motion sequence / 按特定任务的运动过程拾取、转移、翻转、对准或交接工件 |
| None of the Available Classes / 不属于任何可用类别 | – | Main function outside handling technology or kinematics not covered by the other classes / 主功能不属于操作技术，或其运动学特征不在其他类别的涵盖范围内 |

*Note: R = number of rotary actuators, T = number of translational actuators, counted according to the rules in Section 4.2.2. Summary of the class definitions; the complete definitions and characteristic features are given in Appendix A.*

注：R 为旋转执行器数量，T 为平移执行器数量，按第 4.2.2 节的规则统计。表中列出类别定义的摘要，完整定义和特征见附录 A。

**③ 组合单元**

The Combined Unit class covers assemblies that perform a motion sequence specific to a handling task, combining translational and rotary movements or several translational movements, often with an integrated end effector, as in an assembly with a lifting axis, a swivel unit and a gripper. It thereby differs from the Multi-Axis System (Gantry), which provides a freely addressable workspace, and from the Robot, which uses exclusively rotary joints.

组合单元包括按特定操作任务执行运动过程的装配体。这类装配体将平移运动与旋转运动相结合，或将多个平移运动相结合，通常还集成末端执行器，例如由升降轴、摆动单元和夹爪组成的装配体。这些特点将组合单元与多轴系统（龙门）和机器人区分开来。多轴系统具有可自由到达各位置的工作空间，机器人则仅使用旋转关节。

**④ 不属于任何可用类别**

The class *None of the Available Classes* covers assemblies whose main function is not a handling function, such as joining, testing, measuring, protective enclosures or frames, as well as handling assemblies whose kinematics are not meaningfully captured by the six handling classes. Machine frames, operator panels mounted on swivel arms and sensor units are typical examples from the dataset. This class makes the coverage of the scheme measurable. The class is reserved for cases that meet its definition, while uncertainty and ambiguity in difficult or ambiguous cases are recorded in separate fields (Section 4.3).

“不属于任何可用类别”涵盖主功能不属于操作功能的装配体，例如用于接合、检测或测量的装配体，以及防护罩和机架。它也涵盖具有操作功能、但其运动学特征无法由六个操作功能类别合理描述的装配体。数据集中的典型例子包括设备机架、安装在摆臂上的操作面板和传感器单元。设置这一类别使分类体系的覆盖程度可以量化。只有符合该类别定义的装配体才归入此类。难以判断或存在歧义的案例所涉及的不确定性和歧义分别记录在专门的字段中（第 4.3 节）。

### 4.2.2 Decision Logic | 决策逻辑

**⑤ 识别运动过程与主功能**

Classification follows a fixed sequence of steps. First, the motion sequence and the main function of the assembly are identified. Unless the image clearly shows the motion sequence, the designation and image must be supplemented by at least one additional source from Teamcenter or DFC, such as the 3D view, the drawing or the bill of materials.

分类按固定步骤进行。第一步是识别装配体的运动过程和主功能。除非从图片即可明确判断运动过程，否则除了名称和图片，还必须至少查阅 Teamcenter 或 DFC 中的一种补充资料，例如三维视图、图纸或物料清单。

**⑥ 统计执行器**

Second, the actuators are counted. The count includes only actuators that perform the main function and provide an independent direction of motion. Actuators for auxiliary functions such as clamping or locking, actuators within end effectors such as those generating the gripping motion, and manual adjustment axes are excluded. When multiple actuators act in the same direction, they count as one, as in the case of two parallel cylinders that produce a single stroke.

第二步是统计执行器。仅统计实现主功能且能产生独立运动方向的执行器。用于夹紧或锁定等辅助功能的执行器、位于末端执行器内部的执行器（例如产生夹持动作的执行器），以及手动调节轴均不计入。如果多个执行器沿同一方向作用，则合计为一个，例如共同实现同一行程的两个并联气缸。

**⑦ 根据 R 和 T 确定类别**

Third, the resulting actuator counts R and T are used to determine the class (Figure 4.2). If the main function is not a handling function, the assembly is assigned to *None of the Available Classes*. For assemblies with a handling function, the class is identified using a decision table with R in the rows and T in the columns. Two cases require an additional check. An assembly with no counted actuators (R = 0, T = 0) is assigned to Gripper if it has a gripping function and to *None of the Available Classes* otherwise. Assemblies with several translational axes and no rotation (R = 0, T ≥ 2) are classified as Gantry only if the axes are orthogonal, at least two of them are horizontal and the first horizontal axis is guided on both sides; otherwise, they are classified as Combined Unit.

第三步是根据统计得到的执行器数量 R 和 T 确定类别（图 4.2）。如果装配体的主功能不属于操作功能，则归入“不属于任何可用类别”。如果主功能属于操作功能，则用 R 查找决策表中的行、用 T 查找列，以确定类别。有两种情况需要进一步判断。若装配体没有计入的执行器（R = 0，T = 0），则有夹持功能时归为夹爪，否则归入“不属于任何可用类别”。若装配体具有多个平移轴且没有旋转（R = 0，T ≥ 2），只有在各轴相互正交、至少两个轴为水平轴且第一个水平轴采用双侧导向时，才归为龙门，否则归为组合单元。

**[Insert Figure 4.2 here / 在此插入图 4.2]**

*Figure 4.2. Classification decision flowchart / 图 4.2 分类决策流程图*

**⑧ 核对类别与边界案例**

Finally, the result is cross-checked against the class definitions and eight documented borderline cases. A gripper mounted on a lifting cylinder, for example, is assigned to Linear Unit because the gripper is treated as an end effector and the lifting axis is the only axis counted. An articulated robot on an additional linear axis, in contrast, is classified as Combined Unit, since its kinematics are no longer exclusively rotary. Appendix A contains the full codebook and all borderline cases.

最后，对照类别定义和八个已记录的边界案例核对分类结果。例如，安装在升降气缸上的夹爪归为直线单元，因为夹爪被视为末端执行器，仅统计升降轴。相比之下，安装在附加直线轴上的关节机器人归为组合单元，因为它的运动学同时涉及旋转和平移。附录 A 收录了完整的 Codebook 及全部边界案例。

## 4.3 Workshop Design and Implementation | Workshop 设计与实施

**① Workshop 目标**

The labeling workshop aimed both to validate the classification scheme using real assemblies and to record the classifications made by participants and the time they took for each assembly. The recorded classifications serve as the basis for correcting the preliminary ground truth, which consisted of the initial labels assigned before the workshop.

标注研讨会旨在用实际装配体验证分类体系，同时记录参与者的分类结果及其对每个装配体进行分类所用的时间。记录的分类结果用于修正初步的 Ground Truth。该初步 Ground Truth 由研讨会前分配的初始标签组成。

**② 分类模板**

Classifications were recorded in an Excel template with one row per assembly (Figure 4.3). For each assembly, participants were required to record a class and rate their confidence on a four-level scale from certain to uncertain. If a second class was plausible, it was entered as a second choice. When participants based a decision on documentation beyond the information in the template, they noted the decisive source, such as the 3D view, the drawing or the bill of materials. A short note was required for uncertain classifications, for the class None of the Available Classes and whenever a second choice was given. The confidence rating therefore indicates how certain participants were about their classification, while the second choice records ambiguity between classes. A timestamp was recorded automatically for each entry, from which the processing time per assembly was derived.

分类结果记录在 Excel 模板中，每个装配体占一行（图 4.3）。对于每个装配体，参与者必须填写类别，并按从“确定”到“不确定”的四级量表评定置信度。如果另一个类别也合理，则将其填为第二选择。如果参与者依据模板所提供信息之外的资料作出判断，则需注明起决定作用的资料来源，例如三维视图、图纸或物料清单。分类不确定、归入“不属于任何可用类别”或填写了第二选择时，都需要附上一条简短备注。因此，置信度反映参与者对分类结果的确定程度，第二选择记录类别之间的歧义。每条记录都会自动生成时间戳，并据此计算每个装配体的处理时间。

**[Insert Figure 4.3 here / 在此插入图 4.3]**

*Figure 4.3. Simplified structure of the classification template used in the labeling workshop / 图 4.3 标注研讨会所用分类模板的简化结构*

**③ 实施过程**

The workshop took place over four sessions and involved 16 participants, including four engineers and 12 students. All sessions followed the same procedure. To establish a common basis for classification, participants began by spending approximately ten minutes reading the codebook. They then classified the assemblies individually, using Teamcenter and DFC for further research where required, with a time budget of approximately two minutes per assembly. Participants each classified a subset of the assemblies, with five to ten participants independently classifying each assembly.

研讨会分四次举行，共有 16 人参加，其中 4 名工程师、12 名学生。每次研讨会都采用相同的流程。为建立统一的分类基础，参与者首先花约 10 分钟阅读 Codebook。随后，参与者各自对装配体进行分类，必要时通过 Teamcenter 和 DFC 查阅补充资料。每个装配体的分类时间预算约为 2 分钟。每名参与者负责其中一部分装配体，每个装配体均由 5 至 10 名参与者独立分类。

## 4.4 Evaluation Procedure | 评价方法

**① 评价步骤**

The evaluation of the workshop results involved three steps, beginning with a review of the classifications against the codebook, followed by the assignment of each assembly to an ambiguity regime and the measurement of agreement among participants.

研讨会结果分三步进行评价。首先对照 Codebook 复核分类结果，然后将每个装配体归入一个歧义类别（ambiguity regime），最后量化参与者之间的一致性。

**② 复核**

For each assembly, the participants' classifications were compared with the initial label and reviewed by two persons against the codebook and the original documentation, such as the 3D view, the drawing and the bill of materials. The reviewers based their decisions on the documentation and the codebook rules, regardless of which class received the most votes. Where the review showed that the initial label did not comply with the codebook, the label was corrected.

对每个装配体，先将参与者的分类结果与初始标签进行比较，再由两人对照 Codebook 和原始资料进行复核。原始资料包括三维视图、图纸和物料清单等。复核人员依据资料和 Codebook 的规则作出判断，票数最多的类别不影响这一判断。如果复核发现初始标签不符合 Codebook，就修正该标签。

**③ Ambiguity regime 的定义**

The review was used to assign each assembly to one of three ambiguity regimes according to how clearly a single class could be determined. In regime E1, all participants chose the same class, and the review confirmed that this class complies with the codebook. In regime E2, some participants selected a different class, but the review confirmed that applying the codebook rules yielded a single class and that the documentation did not support the alternative classifications. In regime M, participants disagreed, and the review showed that the documentation and the codebook support more than one class. Participants disagreed in both E2 and M, but the codebook resolved the disagreement only in E2.

根据复核结果，每个装配体被归入三个歧义类别之一，具体取决于能否明确判定唯一的功能类别。在 E1 中，所有参与者都选择了同一类别，复核确认该类别符合 Codebook。在 E2 中，部分参与者选择了其他类别，但复核确认，按 Codebook 的规则只能得出一个类别，且资料不支持其他分类结果。在 M 中，参与者意见不一致，复核表明资料和 Codebook 支持不止一个类别。E2 和 M 都存在分歧，但只有在 E2 中，Codebook 能够解决这种分歧。

Figure 4.4 illustrates the three regimes with one example each. All participants assigned the articulated robot to the same class, and the review confirmed that classification. For the mounting part, one participant chose Gripper, but the assembly has no gripping function, so the codebook leads to None of the Available Classes. A secondary rotary component in the lifting unit contributes indirectly to the lifting motion, which allows the assembly to be interpreted as either a Linear Unit or a Combined Unit. Both classes were therefore allowed.

图 4.4 为每种 regime 各举了一个例子。关节机器人的分类完全一致，复核确认了该标签。固定件有一名参与者选了夹爪，但它没有夹持功能，因此按 Codebook 应归为“不属于任何可用类别”。升降单元中，一个次要的旋转部件间接参与了升降运动，因此它既可以理解为直线单元，也可以理解为组合单元，两个类别都被允许。

**[Insert Figure 4.4 here / 在此插入图 4.4]**

*Figure 4.4. Examples of the three ambiguity regimes. Numbers in parentheses indicate the share of participants who chose each class (illustrative excerpt) / 图 4.4 三种 ambiguity regime 的示例。括号中的数字表示选择该类别的参与者比例（示意节选）*

**④ 允许标签集合**

The review thereby yielded a set of allowed labels for each assembly. Each assembly in regime E1 or E2 has exactly one allowed class. For assemblies in regime M, it contains all classes that were found in the review to be consistent with the documentation and the codebook.

复核由此为每个装配体确定了一个允许标签集合。E1 或 E2 中的每个装配体只有一个允许类别。对于 M 中的装配体，集合包含复核认定与资料和 Codebook 一致的所有类别。

**⑤ 为什么选 Krippendorff's α**

Krippendorff's α was used to measure agreement among participants (Section 2.5). The coefficient suits the workshop design for three reasons: it accommodates any number of annotators, it does not require each assembly to be classified by the same annotators, and it is defined for nominal data such as functional classes. The workshop required these properties because each assembly was classified by five to ten participants and the group of participants varied across assemblies.

采用 Krippendorff's α 衡量参与者之间的一致性（第 2.5 节）。这一系数适合本研讨会的设计，因为它允许任意数量的标注者，允许不同装配体由不同的标注者分类，也适用于功能类别这类名义尺度数据。由于每个装配体由 5 至 10 名参与者分类，且参与者组合随装配体而异，因此本研讨会需要这些特性。

**⑥ α 的计算范围**

α was calculated for the assemblies in regimes E1 and E2 across the entire dataset, without distinguishing between the primary and the supplementary set. The review confirmed that disagreement in regime M reflects ambiguity, so an agreement coefficient for this regime alone would not be meaningful. Because the regimes were themselves assigned partly on the basis of participant agreement, restricting the calculation to E1 and E2 tends to raise α; the value for all assemblies is therefore reported for comparison. The calculation was performed in Excel using Krippendorff's method for nominal data.

α 的计算涵盖整个数据集中属于 E1 和 E2 的装配体，主数据集和补充数据集合并计算。复核确认 M 中的分歧反映了实际歧义，因此单独为 M 计算一致性系数没有解释意义。由于歧义类别的划分本身部分依据参与者的一致程度，仅对 E1 和 E2 计算往往会使 α 升高。因此，另外报告基于全部装配体计算的 α 作为对照。计算在 Excel 中完成，采用 Krippendorff 针对名义尺度数据的方法。

**⑦ 处理时间**

The timestamps were used to determine processing times and calculate the mean time per assembly separately for engineers and students.

根据时间戳确定处理时间，并分别计算工程师和学生处理每个装配体的平均用时。

## 4.5 Results | 结果

The workshop results are organized into three parts covering the outcome of the ground truth review and the resulting distribution of ambiguity regimes, agreement among participants, and the time required for classification. All results refer to the ground truth before the LLM experiments; its final revision is described in Chapter 5.

研讨会结果分三部分呈现：Ground Truth 的复核结果及由此得出的歧义类别（ambiguity regime）分布、参与者之间的一致性，以及分类所需的时间。所有结果均基于 LLM 实验前的 Ground Truth，其最终修订见第 5 章。

### 4.5.1 GT Review and Regime Distribution | Ground Truth 复核与 Regime 分布

**① 复核结果概述**

The review described in Section 4.4 assigned 122 of the 199 assemblies (61.3 %) to regime E1, 49 (24.6 %) to E2 and 28 (14.1 %) to M. The review therefore yielded an unambiguous classification for 85.9 % of the assemblies. In the course of the review, two labels were corrected because they did not comply with the codebook: in both cases, an assembly initially labelled as Combined Unit was reassigned, once to Linear Unit and once to Multi-Axis System (Gantry). Both assemblies fell into regime M, and Combined Unit remained an additional allowed label for each. For the other assemblies in regime M, the initial label was likewise retained as the primary label and supplemented by the further classes that the review found to be consistent with the documentation and the codebook.

经过第 4.4 节所述的复核，199 个装配体中有 122 个（61.3%）归入 E1，49 个（24.6%）归入 E2，28 个（14.1%）归入 M。因此，85.9% 的装配体可以明确分类。复核过程中，有两个标签因不符合 Codebook 而被修正。两个装配体的初始标签均为组合单元，复核后一个改为直线单元，另一个改为多轴系统（龙门）。这两个装配体均归入 M，并各自保留组合单元作为额外的允许标签。其余 M 类装配体同样保留初始标签作为主标签，并补充复核认定符合资料和 Codebook 的其他类别。

**② 各类别的情况**

The highest counts in regime M were recorded for Gripper (7 assemblies), Robot and Rotary Unit (6 each), while no assembly classified as None of the Available Classes fell into regime M.

归入 M 的装配体以夹爪最多（7 个），其次是机器人和旋转单元（各 6 个）。归为“不属于任何可用类别”的装配体均未归入 M。

**③ M 类的标签组合**

Combined Unit was among the allowed labels for 17 of the 28 assemblies in regime M. Robot and Combined Unit formed the most common pair of allowed labels (6 assemblies), followed by Multi-Axis System (Gantry) and Combined Unit (4 assemblies). In the robot cases, [reason].

在 28 个归入 M 的装配体中，有 17 个的允许标签包含组合单元。最常见的允许标签组合是机器人与组合单元（6 个装配体），其次是多轴系统（龙门）与组合单元（4 个装配体）。在涉及机器人的这些案例中，[原因]。

### 4.5.2 Inter-Annotator Agreement | 标注者间一致性

Krippendorff's α was 0.806 when calculated for the assemblies in regimes E1 and E2. This value exceeds the threshold of 0.800 and thus indicates reliable agreement (Section 2.5). Including regime M in the analysis of the full dataset yielded an α of 0.751, which falls between 0.667 and 0.800 and supports only tentative conclusions. The difference between the two values reflects the exclusion of the assemblies whose classification remained ambiguous after the review. The level of agreement for assemblies with an unambiguous classification indicates that the codebook supports consistent classification and that the reviewed ground truth provides a suitable reference for the LLM experiments in Chapter 5.

基于 E1 和 E2 的装配体计算，Krippendorff's α 为 0.806。这一数值高于 0.800 的阈值，表明参与者之间的一致性可靠（第 2.5 节）。纳入全部装配体（包括 M）后，α 为 0.751，介于 0.667 和 0.800 之间，因此只能据此得出初步结论。两个数值的差异反映了排除复核后仍有分类歧义的装配体所产生的影响。对于能够明确分类的装配体，一致性结果表明 Codebook 能够支持一致的分类，复核后的 Ground Truth 也适合作为第 5 章 LLM 实验的参考。

### 4.5.3 Annotation Time | 标注用时

The engineers required a mean of 31 s per assembly and the students 42 s. These times include the research in Teamcenter and DFC that participants carried out where required.

工程师平均每个装配体用时 31 秒，学生平均用时 42 秒。这些用时包含了参与者在需要时到 Teamcenter 和 DFC 中查阅资料的时间。

## 4.6 Implications for the LLM Evaluation | 对 LLM 评价的意义

**① 概述**

The evaluation of LLM-based classification in Chapter 5 is guided by the workshop results. They provide the reference labels, the basis for distinguishing between unambiguous and ambiguous assemblies and a human baseline for the time required.

第 5 章以研讨会结果为依据，评价基于 LLM 的分类。研讨会结果提供了参考标签、区分分类明确与存在歧义的装配体的依据，以及分类用时的人工基准。

**② 按 regime 分别评价**

Since the regimes differ in how unambiguously an assembly can be classified, the LLM results are reported separately for E1, E2 and M in addition to the overall result. An error in E1 represents a departure from a clear human judgement, since all participants assigned the same class to the assembly. Regime E2 shows whether the LLM applies the codebook rules correctly in cases where individual participants deviated. Because the documentation and the codebook support multiple classes in regime M, the results for this regime are interpreted differently.

各个 regime 的分类明确程度不同，因此除了总体结果外，LLM 的结果还按 E1、E2 和 M 分别报告。在 E1 中，所有参与者都为同一个装配体选了相同的类别，因此模型分类出错就意味着偏离了明确的人工判断。E2 用于检验在个别参与者的分类出现偏差时，LLM 是否正确运用了 Codebook 的规则。由于在 M 中，资料和 Codebook 支持多个类别，因此需要用不同的方式解读这一 regime 的结果。

**③ Allowed-Label-Set Accuracy**

The main metric is therefore the Allowed-Label-Set Accuracy (hereafter Allowed Accuracy). A classification counts as correct if the predicted class is contained in the set of allowed labels of the assembly (Section 4.4). Each assembly in regimes E1 and E2 has exactly one allowed class, so the metric is equivalent to conventional accuracy for these assemblies. For assemblies in regime M, a prediction of any allowed class counts as correct, even if it differs from the primary label.

因此，采用 Allowed-Label-Set Accuracy（下文简称 Allowed Accuracy）作为主要评价指标。如果预测类别属于该装配体的允许标签集合（第 4.4 节），则该次分类计为正确。E1 和 E2 中的每个装配体都只有一个允许类别，因此对于这些装配体，该指标等同于常规准确率。对于 M 中的装配体，只要预测的是任一允许类别，即使与主标签不同，也计为正确。

**④ 过渡到第 5 章**

Chapter 5 builds on these results. After describing the experimental setup and configurations, the chapter evaluates LLM-based classification against the reviewed ground truth and compares the processing times with those of the human classification.

第 5 章在这些结果的基础上展开。该章先介绍实验设置和配置，再以复核后的 Ground Truth 为参考，评价基于 LLM 的分类，并与人工处理时间进行比较。

## 待处理

- 第 ④ 段的 DFC 官方文件引用，以及 Teamcenter 和 Autodesk Vault 的关系（BMG 如果两者都在用，加一句说明）。
- 表 4.1 的数字在复核后如有变化，记得同步更新第 ⑤ 段的“22 至 31”和“29”。

### 4.4 待办

- [ ] 复核 α：按 199 个装配体重新计算时，用 Python（例如 krippendorff 包）独立算一次，确认和 Excel 的结果一致。如果一致，在⑥最后一句补上 “and verified with …”。

### 4.5 待办

- [ ] 4.5.1 ③ 的 [reason]：补充机器人那几个例子为什么也允许组合单元。行 32、35、40、42、99、127 都是这种情况，如果原因不一样，写最常见的那种。

### 4.6 待办

- [ ] **是否提主数据集和补充数据集的差别**：M 类有 27 个在主数据集，补充数据集只有 1 个，可能影响 5.8 的验证结果。可以留到第 5 章或第 7 章再说。
