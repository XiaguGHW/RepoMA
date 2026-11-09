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

## 待处理

- 第 ④ 段的 DFC 官方文件引用，以及 Teamcenter 和 Autodesk Vault 的关系（BMG 如果两者都在用，加一句说明）。
- 表 4.1 的数字在复核后如有变化，记得同步更新第 ⑤ 段的“22 至 31”和“29”。
