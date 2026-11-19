package com.example.dto.camera;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 摄像头设备更新DTO
 */
@Data
public class CameraUpdateDTO {
    /**
     * 设备ID
     */
    @NotNull(message = "设备ID不能为空")
    private Long id;

    /**
     * 设备名称
     */
    @NotBlank(message = "设备名称不能为空")
    @jakarta.validation.constraints.Size(max=100)
    private String name;

    /**
     * 安装位置
     */
    @NotBlank(message = "安装位置不能为空")
    @jakarta.validation.constraints.Size(max=200)
    private String location;

    /**
     * IP地址
     */
    @jakarta.validation.constraints.Size(max=50)
    private String ipAddress;

    /**
     * RTSP地址
     */
    @jakarta.validation.constraints.Size(max=1000)
    @lombok.ToString.Exclude
    private String rtspUrl;

    /**
     * 状态(0:离线 1:在线 2:故障)
     */
    @jakarta.validation.constraints.Min(0) @jakarta.validation.constraints.Max(3)
    private Integer status;

    /**
     * 故障类型(network:网络故障 hardware:硬件故障 software:软件故障 power:电源故障 other:其他故障)
     */
    @jakarta.validation.constraints.Size(max=50)
    private String faultType;

    /**
     * 经度
     */
    @jakarta.validation.constraints.DecimalMin("-180") @jakarta.validation.constraints.DecimalMax("180")
    private Double longitude;  // 新增字段

    /**
     * 纬度
     */
    @jakarta.validation.constraints.DecimalMin("-90") @jakarta.validation.constraints.DecimalMax("90")
    private Double latitude;   // 新增字段
} 