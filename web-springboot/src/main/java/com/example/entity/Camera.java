package com.example.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.time.LocalDateTime;

/**
 * 摄像头设备实体类
 */
@Data
@TableName("camera")
public class Camera {
    @TableField(exist = false)
    private java.util.Map<String,Object> riskRule;
    /**
     * 设备ID
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 设备名称
     */
    private String name;

    /**
     * 安装位置
     */
    private String location;

    /**
     * IP地址
     */
    private String ipAddress;

    /**
     * RTSP地址
     */
    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    @lombok.ToString.Exclude
    private String rtspUrl;

    @TableLogic
    private Integer deleted;

    /**
     * 状态(0:离线 1:在线 2:故障)
     */
    private Integer status;

    /**
     * 故障类型
     */
    private String faultType;

    /**
     * 经度
     */
    private Double longitude;  // 新增字段

    /**
     * 纬度
     */
    private Double latitude;   // 新增字段

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
} 