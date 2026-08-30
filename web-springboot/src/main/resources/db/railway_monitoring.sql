DROP DATABASE IF EXISTS railway_monitoring;
CREATE DATABASE IF NOT EXISTS railway_monitoring DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE railway_monitoring;
-- ----------------------------
-- Table structure for abnormal_event
-- ----------------------------
DROP TABLE IF EXISTS `abnormal_event`;
CREATE TABLE `abnormal_event`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '事件ID',
  `camera_id` bigint NOT NULL COMMENT '关联摄像头ID',
  `event_time` datetime NOT NULL COMMENT '事件发生时间',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '发生位置',
  `level` tinyint NOT NULL COMMENT '异常等级(1-5)',
  `type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '异常类型',
  `status` tinyint NOT NULL DEFAULT 0 COMMENT '处理状态(0:未处理 1:处理中 2:已处理)',
  `image_url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '视频文件URL',
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '事件描述',
  `handler_id` bigint NULL DEFAULT NULL COMMENT '处理人ID',
  `handle_time` datetime NULL DEFAULT NULL COMMENT '处理时间',
  `handle_result` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL COMMENT '处理结果',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 246 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '异常事件记录表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of abnormal_event
-- ----------------------------
INSERT INTO `abnormal_event` VALUES (209, 5, '2025-11-18 11:00:18', '接触网支柱旁', 2, '牛', 2, '待上传', '物体【牛】（ID: 11）在视频时间段「2025-11-18 19:00:05.318701 至 2025-11-18 19:00:16.248352」内被检测到，位置：接触网支柱旁，最高置信度：72.0%', 1, '2025-11-23 22:00:55', '处理好了。', '2025-11-18 19:00:18', '2025-11-18 19:00:18');
INSERT INTO `abnormal_event` VALUES (210, 5, '2025-11-18 11:00:18', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 6）在视频时间段「2025-11-18 19:00:05.318701 至 2025-11-18 19:00:16.248352」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-11-18 19:00:18', '2025-11-18 19:00:18');
INSERT INTO `abnormal_event` VALUES (211, 5, '2025-11-18 11:00:18', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 9）在视频时间段「2025-11-18 19:00:05.318701 至 2025-11-18 19:00:16.248352」内被检测到，位置：接触网支柱旁，最高置信度：67.0%', NULL, NULL, NULL, '2025-11-18 19:00:18', '2025-11-18 19:00:18');
INSERT INTO `abnormal_event` VALUES (212, 5, '2025-11-23 14:31:45', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 6）在视频时间段「2025-11-23 22:31:31.680442 至 2025-11-23 22:31:43.990174」内被检测到，位置：接触网支柱旁，最高置信度：68.0%', NULL, NULL, NULL, '2025-11-23 22:31:45', '2025-11-23 22:31:45');
INSERT INTO `abnormal_event` VALUES (213, 5, '2025-11-23 14:31:45', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 4）在视频时间段「2025-11-23 22:31:31.680442 至 2025-11-23 22:31:43.990174」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-11-23 22:31:45', '2025-11-23 22:31:45');
INSERT INTO `abnormal_event` VALUES (214, 5, '2025-11-23 14:31:45', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 5）在视频时间段「2025-11-23 22:31:31.680442 至 2025-11-23 22:31:43.990174」内被检测到，位置：接触网支柱旁，最高置信度：72.0%', NULL, NULL, NULL, '2025-11-23 22:31:45', '2025-11-23 22:31:45');
INSERT INTO `abnormal_event` VALUES (215, 2, '2025-11-23 14:47:18', '隧道入口', 1, '坑洞', 0, '待上传', '物体【坑洞】（ID: 9）在视频时间段「2025-11-23 22:47:09.056707 至 2025-11-23 22:47:16.878772」内被检测到，位置：隧道入口，最高置信度：39.0%', NULL, NULL, NULL, '2025-11-23 22:47:18', '2025-11-23 22:47:18');
INSERT INTO `abnormal_event` VALUES (216, 2, '2025-11-23 14:47:18', '隧道入口', 1, '坑洞', 0, '待上传', '物体【坑洞】（ID: 13）在视频时间段「2025-11-23 22:47:09.056707 至 2025-11-23 22:47:16.878772」内被检测到，位置：隧道入口，最高置信度：32.0%', NULL, NULL, NULL, '2025-11-23 22:47:18', '2025-11-23 22:47:18');
INSERT INTO `abnormal_event` VALUES (217, 2, '2025-11-23 14:47:18', '隧道入口', 1, '坑洞', 0, '待上传', '物体【坑洞】（ID: 17）在视频时间段「2025-11-23 22:47:09.056707 至 2025-11-23 22:47:16.878772」内被检测到，位置：隧道入口，最高置信度：58.0%', NULL, NULL, NULL, '2025-11-23 22:47:18', '2025-11-23 22:47:18');
INSERT INTO `abnormal_event` VALUES (218, 2, '2025-11-23 14:47:18', '隧道入口', 1, '坑洞', 0, '待上传', '物体【坑洞】（ID: 11）在视频时间段「2025-11-23 22:47:09.056707 至 2025-11-23 22:47:16.878772」内被检测到，位置：隧道入口，最高置信度：50.0%', NULL, NULL, NULL, '2025-11-23 22:47:18', '2025-11-23 22:47:18');
INSERT INTO `abnormal_event` VALUES (219, 5, '2025-11-24 03:52:59', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 3）在视频时间段「2025-11-24 11:52:35.763649 至 2025-11-24 11:52:57.744698」内被检测到，位置：接触网支柱旁，最高置信度：76.0%', NULL, NULL, NULL, '2025-11-24 11:52:59', '2025-11-24 11:52:59');
INSERT INTO `abnormal_event` VALUES (220, 5, '2025-11-24 03:52:59', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-11-24 11:52:35.763649 至 2025-11-24 11:52:57.744698」内被检测到，位置：接触网支柱旁，最高置信度：71.0%', NULL, NULL, NULL, '2025-11-24 11:52:59', '2025-11-24 11:52:59');
INSERT INTO `abnormal_event` VALUES (221, 5, '2025-11-24 03:52:59', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 4）在视频时间段「2025-11-24 11:52:35.763649 至 2025-11-24 11:52:57.744698」内被检测到，位置：接触网支柱旁，最高置信度：70.0%', NULL, NULL, NULL, '2025-11-24 11:52:59', '2025-11-24 11:52:59');
INSERT INTO `abnormal_event` VALUES (222, 5, '2025-11-24 03:52:59', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 5）在视频时间段「2025-11-24 11:52:35.763649 至 2025-11-24 11:52:57.744698」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-11-24 11:52:59', '2025-11-24 11:52:59');
INSERT INTO `abnormal_event` VALUES (223, 5, '2025-11-24 08:01:21', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-11-24 16:00:48.313035 至 2025-11-24 16:01:19.296377」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-11-24 16:01:21', '2025-11-24 16:01:21');
INSERT INTO `abnormal_event` VALUES (224, 5, '2025-11-24 08:01:21', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 3）在视频时间段「2025-11-24 16:00:48.313035 至 2025-11-24 16:01:19.296377」内被检测到，位置：接触网支柱旁，最高置信度：72.0%', NULL, NULL, NULL, '2025-11-24 16:01:21', '2025-11-24 16:01:21');
INSERT INTO `abnormal_event` VALUES (225, 5, '2025-12-09 14:28:29', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 7）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：68.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (226, 5, '2025-12-09 14:28:29', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (227, 5, '2025-12-09 14:28:29', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 4）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (228, 5, '2025-12-09 14:28:29', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 5）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (229, 5, '2025-12-09 14:28:29', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 8）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (230, 5, '2025-12-09 14:28:29', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 3）在视频时间段「2025-12-09 22:27:27.808078 至 2025-12-09 22:28:27.855124」内被检测到，位置：接触网支柱旁，最高置信度：75.0%', NULL, NULL, NULL, '2025-12-09 22:28:30', '2025-12-09 22:28:30');
INSERT INTO `abnormal_event` VALUES (231, 5, '2025-12-09 15:18:11', '接触网支柱旁', 2, '牛', 2, '待上传', '物体【牛】（ID: 1）在视频时间段「2025-12-09 23:17:51.633061 至 2025-12-09 23:18:09.318509」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', 1, '2025-12-15 10:51:52', '已经解决了。', '2025-12-09 23:18:11', '2025-12-09 23:18:11');
INSERT INTO `abnormal_event` VALUES (232, 5, '2025-12-09 15:18:11', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 5）在视频时间段「2025-12-09 23:17:51.633061 至 2025-12-09 23:18:09.318509」内被检测到，位置：接触网支柱旁，最高置信度：68.0%', NULL, NULL, NULL, '2025-12-09 23:18:11', '2025-12-09 23:18:11');
INSERT INTO `abnormal_event` VALUES (233, 5, '2025-12-09 15:18:11', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-12-09 23:17:51.633061 至 2025-12-09 23:18:09.318509」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-12-09 23:18:11', '2025-12-09 23:18:11');
INSERT INTO `abnormal_event` VALUES (234, 5, '2025-12-09 15:18:11', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 3）在视频时间段「2025-12-09 23:17:51.633061 至 2025-12-09 23:18:09.318509」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 23:18:11', '2025-12-09 23:18:11');
INSERT INTO `abnormal_event` VALUES (235, 5, '2025-12-09 15:18:11', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 6）在视频时间段「2025-12-09 23:17:51.633061 至 2025-12-09 23:18:09.318509」内被检测到，位置：接触网支柱旁，最高置信度：69.0%', NULL, NULL, NULL, '2025-12-09 23:18:11', '2025-12-09 23:18:11');
INSERT INTO `abnormal_event` VALUES (236, 5, '2025-12-09 15:24:33', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-12-09 23:24:00.730351 至 2025-12-09 23:24:31.164405」内被检测到，位置：接触网支柱旁，最高置信度：76.0%', NULL, NULL, NULL, '2025-12-09 23:24:33', '2025-12-09 23:24:33');
INSERT INTO `abnormal_event` VALUES (237, 5, '2025-12-09 15:24:33', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 7）在视频时间段「2025-12-09 23:24:00.730351 至 2025-12-09 23:24:31.164405」内被检测到，位置：接触网支柱旁，最高置信度：70.0%', NULL, NULL, NULL, '2025-12-09 23:24:33', '2025-12-09 23:24:33');
INSERT INTO `abnormal_event` VALUES (238, 5, '2025-12-09 15:24:33', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 6）在视频时间段「2025-12-09 23:24:00.730351 至 2025-12-09 23:24:31.164405」内被检测到，位置：接触网支柱旁，最高置信度：28.0%', NULL, NULL, NULL, '2025-12-09 23:24:33', '2025-12-09 23:24:33');
INSERT INTO `abnormal_event` VALUES (239, 5, '2025-12-09 15:24:33', '接触网支柱旁', 1, '牛', 0, '待上传', '物体【牛】（ID: 9）在视频时间段「2025-12-09 23:24:00.730351 至 2025-12-09 23:24:31.164405」内被检测到，位置：接触网支柱旁，最高置信度：69.0%', NULL, NULL, NULL, '2025-12-09 23:24:33', '2025-12-09 23:24:33');
INSERT INTO `abnormal_event` VALUES (240, 5, '2025-12-09 15:24:33', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 8）在视频时间段「2025-12-09 23:24:00.730351 至 2025-12-09 23:24:31.164405」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-09 23:24:33', '2025-12-09 23:24:33');
INSERT INTO `abnormal_event` VALUES (241, 5, '2025-12-14 14:13:49', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 2）在视频时间段「2025-12-14 22:13:16.474124 至 2025-12-14 22:13:47.482506」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-12-14 22:13:49', '2025-12-14 22:13:49');
INSERT INTO `abnormal_event` VALUES (242, 5, '2025-12-14 14:13:49', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 3）在视频时间段「2025-12-14 22:13:16.474124 至 2025-12-14 22:13:47.482506」内被检测到，位置：接触网支柱旁，最高置信度：74.0%', NULL, NULL, NULL, '2025-12-14 22:13:49', '2025-12-14 22:13:49');
INSERT INTO `abnormal_event` VALUES (243, 5, '2025-12-14 14:13:49', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 7）在视频时间段「2025-12-14 22:13:16.474124 至 2025-12-14 22:13:47.482506」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', NULL, NULL, NULL, '2025-12-14 22:13:49', '2025-12-14 22:13:49');
INSERT INTO `abnormal_event` VALUES (244, 5, '2025-12-14 14:13:49', '接触网支柱旁', 2, '牛', 0, '待上传', '物体【牛】（ID: 6）在视频时间段「2025-12-14 22:13:16.474124 至 2025-12-14 22:13:47.482506」内被检测到，位置：接触网支柱旁，最高置信度：68.0%', NULL, NULL, NULL, '2025-12-14 22:13:49', '2025-12-14 22:13:49');
INSERT INTO `abnormal_event` VALUES (245, 5, '2025-12-14 14:13:49', '接触网支柱旁', 2, '牛', 2, '待上传', '物体【牛】（ID: 4）在视频时间段「2025-12-14 22:13:16.474124 至 2025-12-14 22:13:47.482506」内被检测到，位置：接触网支柱旁，最高置信度：73.0%', 1, '2026-01-17 17:59:36', '后', '2025-12-14 22:13:49', '2025-12-14 22:13:49');

-- ----------------------------
-- Table structure for camera
-- ----------------------------
DROP TABLE IF EXISTS `camera`;
CREATE TABLE `camera`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '设备ID',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '设备名称',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '安装位置',
  `ip_address` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT 'IP地址',
  `rtsp_url` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '视频流地址',
  `status` tinyint NOT NULL DEFAULT 1 COMMENT '状态(0:离线 1:在线 2:故障)',
  `fault_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '故障类型',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `longitude` double NULL DEFAULT NULL COMMENT '经度',
  `latitude` double NULL DEFAULT NULL COMMENT '纬度',
  PRIMARY KEY (`id`) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 21 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '摄像头设备表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of camera
-- ----------------------------
INSERT INTO `camera` VALUES (1, 'CAM001', '成都站1号站台', '192.168.1.101', 'rtsp://127.0.0.1:8554/camera_test', 0, NULL, '2025-02-12 01:08:53', '2025-12-09 15:43:18', 101, 36);
INSERT INTO `camera` VALUES (2, 'CAM002', '隧道入口', '192.168.1.102', 'rtsp://localhost:8554/test_video_1', 0, NULL, '2025-02-12 01:08:53', '2025-12-09 15:40:56', 101.6, 36);
INSERT INTO `camera` VALUES (3, 'CAM003', '跨河桥梁中段', '192.168.1.103', 'rtsp://localhost:8554/test_video_2', 0, NULL, '2025-02-12 01:08:53', '2025-12-09 15:40:52', 101.8, 36);
INSERT INTO `camera` VALUES (4, 'CAM004', '调度中心楼顶', '192.168.1.104', 'rtsp://localhost:8554/test_video_3', 0, NULL, '2025-02-12 01:08:53', '2025-12-09 15:40:46', 102, 36);
INSERT INTO `camera` VALUES (5, 'SuperCAM', '接触网支柱旁', '192.168.0.36', 'rtsp://localhost:8554/test_video_4', 1, 'hardware', '2025-02-13 09:52:43', '2025-12-09 15:40:43', 102.2, 36);
INSERT INTO `camera` VALUES (6, 'test1', 'test1', '1.1.1.1', 'rtsp://127.0.0.1:8554/test1', 2, 'other', '2025-10-26 21:34:12', '2025-12-09 15:40:39', 102.4, 36);
INSERT INTO `camera` VALUES (7, 't2', 't2', '1.1.1.2', 'rtsp://127.0.0.1:8554/t2', 2, 'other', '2025-10-26 21:35:11', '2025-12-09 15:40:26', 102.6, 36);
INSERT INTO `camera` VALUES (8, 't3', 't3', '1.1.1.3', 'rtsp://127.0.0.1:8554/t3', 2, 'network', '2025-10-26 21:35:29', '2025-12-09 15:40:20', 102.8, 36);
INSERT INTO `camera` VALUES (9, 't4', 't4', '1.1.1.4', 'rtsp://127.0.0.1:8554/t4', 2, 'hardware', '2025-10-26 21:35:45', '2025-12-09 15:40:08', 103, 36);
INSERT INTO `camera` VALUES (11, 't6', 't6', '1.1.1.6', 'rtsp://127.0.0.1:8554/t6', 2, 'power', '2025-10-26 21:36:11', '2025-12-09 15:39:44', 103.4, 36);
INSERT INTO `camera` VALUES (18, 't8', 't8', '1.1.1.8', 'rtsp://127.0.0.1:8554/t8', 0, NULL, '2025-12-09 12:58:57', '2025-12-09 12:58:57', 103.683584, 36.062458);
INSERT INTO `camera` VALUES (19, 't5', 't5', '1.1.1.5', 'rtsp://127.0.0.1:8554/t5', 0, NULL, '2025-12-09 17:03:23', '2025-12-09 17:03:23', 103.187198, 36.001);
INSERT INTO `camera` VALUES (20, 't9', 't9', '1.1.1.9', 'rtsp://127.0.0.1:8554/t9', 1, NULL, '2025-12-14 21:52:31', '2025-12-14 21:52:31', 103.610456, 36.004821);

-- ----------------------------
-- Table structure for user
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user`  (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户名',
  `password` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '密码',
  `real_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '真实姓名',
  `phone` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '手机号',
  `email` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NULL DEFAULT NULL COMMENT '邮箱',
  `role` tinyint NOT NULL DEFAULT 0 COMMENT '角色(0:普通用户 1:管理员)',
  `status` tinyint NOT NULL DEFAULT 1 COMMENT '状态(0:禁用 1:启用)',
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`) USING BTREE,
  UNIQUE INDEX `username`(`username` ASC) USING BTREE
) ENGINE = InnoDB AUTO_INCREMENT = 7 CHARACTER SET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '用户表' ROW_FORMAT = DYNAMIC;

-- ----------------------------
-- Records of user
-- ----------------------------
INSERT INTO `user` VALUES (1, 'admin', 'e10adc3949ba59abbe56e057f20f883e', '系统管理员', '13800138003', '13800138003@qq.com', 1, 1, '2025-02-12 01:08:53', '2025-02-12 01:08:53');
INSERT INTO `user` VALUES (2, 'test', 'e10adc3949ba59abbe56e057f20f883e', '测试用户', '13800138001', '13800138001@qq.com', 0, 1, '2025-02-12 01:08:53', '2025-02-12 01:08:53');

SET FOREIGN_KEY_CHECKS = 1;
