package com.example;

import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.plugin.*;
import org.apache.ibatis.session.ResultHandler;
import org.apache.ibatis.session.RowBounds;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

/** Test-only scheduling hook: pause a manual operation after its snapshot read. */
@Intercepts({
    @Signature(type=Executor.class,method="query",args={MappedStatement.class,Object.class,RowBounds.class,ResultHandler.class}),
    @Signature(type=Executor.class,method="query",args={MappedStatement.class,Object.class,RowBounds.class,ResultHandler.class,org.apache.ibatis.cache.CacheKey.class,org.apache.ibatis.mapping.BoundSql.class})
})
public class ManualEventRace implements Interceptor {
    static class Plan {
        final CountDownLatch read=new CountDownLatch(1),resume=new CountDownLatch(1);
    }
    private static final AtomicReference<Plan> active=new AtomicReference<>();
    static Plan arm(){var value=new Plan();active.set(value);return value;}
    static void clear(){active.set(null);}
    public Object intercept(Invocation invocation)throws Throwable{
        Object result=invocation.proceed();var plan=active.get();
        var statement=(MappedStatement)invocation.getArgs()[0];
        if(plan!=null && "p0-manual-race".equals(Thread.currentThread().getName()) && statement.getId().endsWith("AbnormalEventMapper.selectById")){
            plan.read.countDown();
            if(!plan.resume.await(10,TimeUnit.SECONDS))throw new AssertionError("manual race schedule timed out");
        }
        return result;
    }
}
