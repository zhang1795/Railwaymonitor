package com.example.security;
import java.io.Serializable;
public record SessionUser(long id,long version) implements Serializable {}
