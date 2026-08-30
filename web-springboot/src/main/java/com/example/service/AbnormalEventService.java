package com.example.service;

import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.service.IService;
import com.example.dto.Abnormal.AbnormalEventCreateDTO;
import com.example.dto.Abnormal.AbnormalEventHandleDTO;
import com.example.dto.Abnormal.AbnormalEventQueryDTO;
import com.example.dto.Abnormal.AbnormalEventUpdateDTO;
import com.example.dto.Abnormal.AbnormalEventVO;
import com.example.entity.AbnormalEvent;

import java.util.List;

/**
 * 异常事件服务接口
 */
public interface AbnormalEventService extends IService<AbnormalEvent> {
    /**
     * 创建异常事件
     *
     * @param dto 创建参数
     * @return 事件ID
     */
    Long createAbnormalEvent(AbnormalEventCreateDTO dto);

    /**
     * 处理异常事件
     *
     * @param dto 处理参数
     */
    void handleAbnormalEvent(AbnormalEventHandleDTO dto);

    /**
     * 分页查询异常事件列表
     *
     * @param dto 查询参数
     * @return 事件列表
     */
    IPage<AbnormalEventVO> getAbnormalEventPage(AbnormalEventQueryDTO dto);

    /**
     * 获取异常事件详情
     *
     * @param id 事件ID
     * @return 事件详情
     */
    AbnormalEventVO getAbnormalEventById(Long id);

    /**
     * 更新异常事件状态
     *
     * @param id     事件ID
     * @param status 状态(0:未处理 1:处理中 2:已处理)
     */
    void updateAbnormalEventStatus(Long id, Integer status);

    /**
     * 删除异常事件
     */
    void deleteAbnormalEvent(Long id);

    /**
     * 批量删除异常事件
     */
    void batchDeleteAbnormalEvents(List<Long> ids);

    /**
     * 更新异常事件
     */
    void updateAbnormalEvent(AbnormalEventUpdateDTO dto);
} 