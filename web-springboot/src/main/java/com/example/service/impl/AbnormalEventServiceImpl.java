package com.example.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.StrUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.example.common.exception.BusinessException;
import com.example.dto.Abnormal.AbnormalEventCreateDTO;
import com.example.dto.Abnormal.AbnormalEventHandleDTO;
import com.example.dto.Abnormal.AbnormalEventQueryDTO;
import com.example.dto.Abnormal.AbnormalEventUpdateDTO;
import com.example.dto.Abnormal.AbnormalEventVO;
import com.example.entity.Camera;
import com.example.entity.AbnormalEvent;
import com.example.entity.User;
import com.example.mapper.AbnormalEventMapper;
import com.example.service.CameraService;
import com.example.service.AbnormalEventService;
import com.example.service.UserService;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

/**
 * 异常事件服务实现类
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AbnormalEventServiceImpl extends ServiceImpl<AbnormalEventMapper, AbnormalEvent> implements AbnormalEventService {

    private final CameraService cameraService;
    private final UserService userService;

    @Value("${file.server.url}")
    private String fileServerUrl;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createAbnormalEvent(AbnormalEventCreateDTO dto) {
        // 校验摄像头是否存在
        Camera camera = cameraService.getById(dto.getCameraId());
        if (camera == null) {
            throw new BusinessException("摄像头不存在");
        }

        // 创建事件
        AbnormalEvent AbnormalEvent = BeanUtil.copyProperties(dto, AbnormalEvent.class);
        // 设置状态为未处理
        AbnormalEvent.setStatus(0);

        // 保存事件
        save(AbnormalEvent);
        
        // 发送异常警报短信
        sendAbnormalAlertSMS(camera, AbnormalEvent);
        
        return AbnormalEvent.getId();
    }

    /**
     * 模拟发送异常警报短信
     */
    private void sendAbnormalAlertSMS(Camera camera, AbnormalEvent AbnormalEvent) {
        // 获取所有管理员用户
        List<User> admins = userService.list(new LambdaQueryWrapper<User>()
                .eq(User::getRole, 1)  // 1表示管理员角色
                .eq(User::getStatus, 1));  // 1表示正常状态
        
        if (admins.isEmpty()) {
            log.warn("没有找到可通知的管理员用户");
            return;
        }
        
        // 格式化时间
        String eventTime = AbnormalEvent.getEventTime().format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
        
        // 构建短信内容
        String smsContent = String.format(
            "【异常预警】检测到异常！\n位置：%s\n时间：%s\n异常等级：%d级\n请及时处理！",
            camera.getLocation(),
            eventTime,
            AbnormalEvent.getLevel()
        );
        
        // 模拟发送短信给每个管理员
        for (User admin : admins) {
            try {
                // 这里是模拟发送短信，实际项目中需要替换为真实的短信发送接口
                log.info("模拟发送短信到 {} ({}): {}", 
                    admin.getRealName(), 
                    admin.getPhone(), 
                    smsContent);
                
                // 在实际项目中，这里需要调用短信服务商的API
                // 例如：smsService.send(admin.getPhone(), smsContent);
                
            } catch (Exception e) {
                log.error("发送短信给管理员{}失败: {}", admin.getRealName(), e.getMessage());
            }
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void handleAbnormalEvent(AbnormalEventHandleDTO dto) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(dto.getId());
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 校验处理人是否存在
        User handler = userService.getById(dto.getHandlerId());
        if (handler == null) {
            throw new BusinessException("处理人不存在");
        }

        // 更新事件信息
        AbnormalEvent.setHandlerId(dto.getHandlerId());
        AbnormalEvent.setHandleTime(LocalDateTime.now());
        AbnormalEvent.setHandleResult(dto.getHandleResult());
        AbnormalEvent.setStatus(2);
        updateById(AbnormalEvent);
    }

    @Override
    public IPage<AbnormalEventVO> getAbnormalEventPage(AbnormalEventQueryDTO dto) {
        // 构建查询条件
        LambdaQueryWrapper<AbnormalEvent> wrapper = new LambdaQueryWrapper<AbnormalEvent>()
                .eq(dto.getCameraId() != null, AbnormalEvent::getCameraId, dto.getCameraId())
                .like(StrUtil.isNotBlank(dto.getLocation()), AbnormalEvent::getLocation, dto.getLocation())
                .eq(dto.getLevel() != null, AbnormalEvent::getLevel, dto.getLevel())
                .eq(dto.getStatus() != null, AbnormalEvent::getStatus, dto.getStatus())
                .eq(dto.getHandlerId() != null, AbnormalEvent::getHandlerId, dto.getHandlerId())
                .ge(dto.getStartTime() != null, AbnormalEvent::getEventTime, dto.getStartTime())
                .le(dto.getEndTime() != null, AbnormalEvent::getEventTime, dto.getEndTime())
                .orderByDesc(AbnormalEvent::getEventTime);

        // 执行分页查询
        IPage<AbnormalEvent> page = page(new Page<>(dto.getCurrent(), dto.getSize()), wrapper);

        // 转换返回结果
        return page.convert(this::convertToVO);
    }

    @Override
    public AbnormalEventVO getAbnormalEventById(Long id) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(id);
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 转换返回结果
        return convertToVO(AbnormalEvent);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateAbnormalEventStatus(Long id, Integer status) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(id);
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 更新状态
        AbnormalEvent.setStatus(status);
        updateById(AbnormalEvent);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateAbnormalEvent(AbnormalEventUpdateDTO dto) {
        // 查询事件
        AbnormalEvent AbnormalEvent = getById(dto.getId());
        if (AbnormalEvent == null) {
            throw new BusinessException("事件不存在");
        }

        // 如果更新了摄像头，校验摄像头是否存在
        if (dto.getCameraId() != null && !dto.getCameraId().equals(AbnormalEvent.getCameraId())) {
            Camera camera = cameraService.getById(dto.getCameraId());
            if (camera == null) {
                throw new BusinessException("摄像头不存在");
            }
        }

        // 更新事件信息
        BeanUtil.copyProperties(dto, AbnormalEvent, "id", "status", "eventTime", "handlerId", "handleTime", "handleResult");
        updateById(AbnormalEvent);
    }

    /**
     * 转换为VO对象
     */
    private AbnormalEventVO convertToVO(AbnormalEvent AbnormalEvent) {
        AbnormalEventVO vo = BeanUtil.copyProperties(AbnormalEvent, AbnormalEventVO.class);

        // 设置摄像头名称
        Camera camera = cameraService.getById(AbnormalEvent.getCameraId());
        if (camera != null) {
            vo.setCameraName(camera.getName());
        }

        // 设置处理人姓名
        if (AbnormalEvent.getHandlerId() != null) {
            User handler = userService.getById(AbnormalEvent.getHandlerId());
            if (handler != null) {
                vo.setHandlerName(handler.getRealName());
            }
        }

        return vo;
    }

    /**
     * 删除异常事件
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteAbnormalEvent(Long id) {
        // 删除前检查记录是否存在
        AbnormalEvent event = getById(id);
        if (event == null) {
            throw new RuntimeException("异常事件不存在");
        }
        
        // 如果有图片，删除图片文件
        if (event.getImageUrl() != null && !event.getImageUrl().isEmpty()) {
            try {
                // 从图片URL中提取bucket和objectKey
                // URL格式：http://localhost:5001/api/file/Abnormal-images/xxx.jpg
                String imageUrl = event.getImageUrl();
                if (imageUrl.startsWith(fileServerUrl)) {
                    String path = imageUrl.substring(fileServerUrl.length());
                    String[] parts = path.split("/");
                    if (parts.length >= 3) {
                        String bucket = parts[1];
                        String objectKey = parts[2];
                        // 调用文件服务删除图片
                        RestTemplate restTemplate = new RestTemplate();
                        restTemplate.delete(fileServerUrl + "/" + bucket + "/" + objectKey);
                    }
                }
            } catch (Exception e) {
                log.error("删除异常事件图片失败: {}", e.getMessage());
                // 继续执行，不影响事件删除
            }
        }
        
        // 执行删除
        removeById(id);
    }

    /**
     * 批量删除异常事件
     */
    @Override
    @Transactional(rollbackFor = Exception.class)
    public void batchDeleteAbnormalEvents(List<Long> ids) {
        // 删除前检查记录是否存在
        List<AbnormalEvent> events = listByIds(ids);
        if (events.size() != ids.size()) {
            throw new RuntimeException("部分异常事件不存在");
        }
        
        // 删除图片文件
        RestTemplate restTemplate = new RestTemplate();
        for (AbnormalEvent event : events) {
            if (event.getImageUrl() != null && !event.getImageUrl().isEmpty()) {
                try {
                    // 从图片URL中提取bucket和objectKey
                    String imageUrl = event.getImageUrl();
                    if (imageUrl.startsWith(fileServerUrl)) {
                        String path = imageUrl.substring(fileServerUrl.length());
                        String[] parts = path.split("/");
                        if (parts.length >= 3) {
                            String bucket = parts[1];
                            String objectKey = parts[2];
                            // 调用文件服务删除图片
                            restTemplate.delete(fileServerUrl + "/" + bucket + "/" + objectKey);
                        }
                    }
                } catch (Exception e) {
                    log.error("删除异常事件图片失败: {}", e.getMessage());
                    // 继续执行，不影响事件删除
                }
            }
        }
        
        // 执行批量删除
        removeBatchByIds(ids);
    }
} 