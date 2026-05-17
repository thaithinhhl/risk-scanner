const { SignJWT } = require("jose");
async function main() {
  const secret = new TextEncoder().encode("G26X1QcTgt0mKoCT7YdAYNv9v7+WGqlA/wZvHIZjTI=");
  const token = await new SignJWT({ email: "test" })
    .setProtectedHeader({ alg: "HS256" })
    .sign(secret);
  console.log("JS Token:", token);
}
main();
