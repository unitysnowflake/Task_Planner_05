local token = os.getenv("TOKEN")

local frandom = io.open("/dev/urandom", "rb")
local d = frandom:read(4)
math.randomseed(d:byte(1) + (d:byte(2) * 256) + (d:byte(3) * 65536) + (d:byte(4) * 4294967296))
frandom:close()

number = math.random(1, 30)

request = function()
    headers = {
        ["Authorization"] = "Bearer " .. token
    }
    return wrk.format("GET", "/users/" .. tostring(number), headers)
end