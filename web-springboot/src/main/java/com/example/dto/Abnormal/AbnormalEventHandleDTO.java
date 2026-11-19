package com.example.dto.Abnormal;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 异常事件处理DTO
 */
@Data
public class AbnormalEventHandleDTO {
    @NotNull @jakarta.validation.constraints.Min(0)
    private Long version;
    /**
     * 事件ID
     */
    @NotNull(message = "事件ID不能为空")
    private Long id;

    /**
     * 处理人ID
     */
    private Long handlerId;

    /**
     * 处理结果
     */
    @NotBlank(message = "处理结果不能为空")
    @jakarta.validation.constraints.Size(max=2000)
    private String handleResult;
}
