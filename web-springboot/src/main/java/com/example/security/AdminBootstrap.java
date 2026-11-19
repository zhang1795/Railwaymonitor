package com.example.security;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import java.nio.charset.StandardCharsets;
import java.sql.DriverManager;
import java.util.Arrays;

/** Explicit offline bootstrap/rotation command; never invoked by app startup. */
public final class AdminBootstrap {
    public static void main(String[] args)throws Exception{
        String username=System.getenv().getOrDefault("P0_ADMIN_USERNAME","admin");
        if(!username.matches("[A-Za-z0-9_-]{3,50}"))throw new IllegalArgumentException("invalid admin username");
        char[] input=System.console()!=null?System.console().readPassword("New administrator password: "):
            new String(System.in.readAllBytes(),StandardCharsets.UTF_8).replaceFirst("[\\r\\n]+$","").toCharArray();
        String password=new String(input);Arrays.fill(input,'\0');
        if(password.length()<12 || password.getBytes(StandardCharsets.UTF_8).length>72)throw new IllegalArgumentException("Password must be >=12 characters and <=72 UTF-8 bytes");
        String encoded=new BCryptPasswordEncoder(12).encode(password);
        String url=System.getenv("DB_URL"),user=System.getenv("DB_USERNAME"),secret=System.getenv("DB_PASSWORD");
        if(url==null || user==null || secret==null)throw new IllegalArgumentException("Explicit DB_URL, DB_USERNAME and DB_PASSWORD required");
        try(var connection=DriverManager.getConnection(url,user,secret)){
            connection.setAutoCommit(false);
            try(var statement=connection.prepareStatement("SELECT id FROM `user` WHERE username=? FOR UPDATE")){
                statement.setString(1,username);
                try(var row=statement.executeQuery()){
                    if(row.next()){
                        try(var update=connection.prepareStatement("UPDATE `user` SET password=?,role=1,status=1,security_version=security_version+1,password_change_required=FALSE WHERE id=?")){
                            update.setString(1,encoded);update.setLong(2,row.getLong(1));update.executeUpdate();
                        }
                    }else try(var insert=connection.prepareStatement("INSERT INTO `user`(username,password,role,status,security_version,password_change_required) VALUES(?,?,1,1,0,FALSE)")){
                        insert.setString(1,username);insert.setString(2,encoded);insert.executeUpdate();
                    }
                }
            }
            try(var revoke=connection.prepareStatement("DELETE FROM preview_grant WHERE user_id IN (SELECT id FROM `user` WHERE username=?)")){
                revoke.setString(1,username);revoke.executeUpdate();
            }
            connection.commit();
        }
        System.out.println("Administrator provisioned; existing sessions invalidated. No password was logged.");
    }
}
