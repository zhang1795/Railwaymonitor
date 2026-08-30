package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.annotation.EnableTransactionManagement;

/**
 * 项目启动类
 */
@SpringBootApplication
@EnableScheduling
@EnableTransactionManagement
public class RailwayMonitoringApplication {
    public static void main(String[] args) {
        SpringApplication.run(RailwayMonitoringApplication.class, args);
    }
} 