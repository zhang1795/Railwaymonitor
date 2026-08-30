package com.example.dto.Abnormal;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 异常事件详情VO
 */
@Data
public class AbnormalEventVO {
    /**
     * 事件ID
     */
    private Long id;

    /**
     * 关联摄像头ID
     */
    private Long cameraId;

    /**
     * 摄像头名称
     */
    private String cameraName;

    /**
     * 事件发生时间
     */
    private LocalDateTime eventTime;

    /**
     * 发生位置
     */
    private String location;

    /**
     * 异常等级(1-5)
     */
    private Integer level;

    /**
     * 检测到的异常物体类型
     */
    private String type;

    /**
     * 处理状态(0:未处理 1:处理中 2:已处理)
     */
    private Integer status;

    /**
     * 现场图片URL
     */
    private String imageUrl;

    /**
     * 事件描述
     */
    private String description;

    /**
     * 处理人ID
     */
    private Long handlerId;

    /**
     * 处理人姓名
     */
    private String handlerName;

    /**
     * 处理时间
     */
    private LocalDateTime handleTime;

    /**
     * 处理结果
     */
    private String handleResult;

    /**
     * 创建时间
     */
    private LocalDateTime createTime;
} 
