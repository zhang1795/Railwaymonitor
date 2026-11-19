package com.example.dto.Abnormal;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
@Schema(description = "异常事件更新DTO")
public class AbnormalEventUpdateDTO {
    @NotNull @jakarta.validation.constraints.Min(0)
    private Long version;
    @jakarta.validation.constraints.Size(max=50)
    private String type;

    @NotNull(message = "事件ID不能为空")
    @Schema(description = "事件ID")
    private Long id;

    @Schema(description = "摄像头ID")
    private Long cameraId;

    @Schema(description = "位置")
    @jakarta.validation.constraints.Size(max=200)
    private String location;

    @Schema(description = "异常等级：0-无异常，1-可疑异常，2-轻微异常，3-中等异常，4-严重异常，5-特别严重")
    @jakarta.validation.constraints.Min(1)
    @jakarta.validation.constraints.Max(5)
    private Integer level;

    @Schema(description = "图片URL")
    @jakarta.validation.constraints.Size(max=1000)
    private String imageUrl;

    @Schema(description = "事件描述")
    @jakarta.validation.constraints.Size(max=2000)
    private String description;
}
