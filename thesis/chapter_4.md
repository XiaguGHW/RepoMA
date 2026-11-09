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

## 待处理

- 第 ④ 段的 DFC 官方文件引用，以及 Teamcenter 和 Autodesk Vault 的关系（BMG 如果两者都在用，加一句说明）。
- 表 4.1 的数字在复核后如有变化，记得同步更新第 ⑤ 段的“22 至 31”和“29”。
